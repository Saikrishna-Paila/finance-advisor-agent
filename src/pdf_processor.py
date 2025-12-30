"""
PDF_PROCESSOR.PY - Extract transactions from bank statement PDFs

This module handles:
1. Reading PDF files (using PyMuPDF)
2. Extracting text from each page
3. Parsing text into structured transactions
4. Handling different bank statement formats

HOW IT WORKS:
=============
Bank PDFs have tables like:

    Date        Description              Amount
    11/01/24    STARBUCKS #1234         -$6.50
    11/01/24    DIRECT DEPOSIT        +$5,000.00

We extract this text and parse it into:
    {
        "date": "2024-11-01",
        "description": "STARBUCKS #1234",
        "amount": -6.50,
        "type": "debit"
    }
"""

import re
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
import pdfplumber


class PDFProcessor:
    """Extract transactions from bank statement PDFs"""

    def __init__(self):
        # Common patterns for parsing transactions
        self.date_patterns = [
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'\d{2}/\d{2}/\d{2}',  # MM/DD/YY
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
        ]

        self.amount_pattern = r'[-+]?\$?[\d,]+\.?\d*'

    def extract_text_pymupdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF using PyMuPDF (fast)

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text as string
        """
        text = ""
        doc = fitz.open(pdf_path)

        for page in doc:
            text += page.get_text()

        doc.close()
        return text

    def extract_tables_pdfplumber(self, pdf_path: str) -> List[pd.DataFrame]:
        """
        Extract tables from PDF using pdfplumber (better for structured tables)

        Args:
            pdf_path: Path to the PDF file

        Returns:
            List of DataFrames, one per table found
        """
        tables = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        df = pd.DataFrame(table[1:], columns=table[0])
                        tables.append(df)

        return tables

    def parse_transactions_from_text(
        self,
        text: str,
        file_id: str
    ) -> List[Dict]:
        """
        Parse raw text into transaction dictionaries

        This is a simplified parser - real bank statements vary greatly.
        You may need to customize this for specific bank formats.

        Args:
            text: Raw text from PDF
            file_id: Unique ID to track which file this came from

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to find a date in the line
            date_match = None
            for pattern in self.date_patterns:
                match = re.search(pattern, line)
                if match:
                    date_match = match.group()
                    break

            if not date_match:
                continue

            # Try to find an amount
            amounts = re.findall(self.amount_pattern, line)
            if not amounts:
                continue

            # Get the last amount (usually the transaction amount)
            amount_str = amounts[-1]
            amount = self._parse_amount(amount_str)

            # Get description (everything between date and amount)
            desc_start = line.find(date_match) + len(date_match)
            desc_end = line.rfind(amount_str)
            description = line[desc_start:desc_end].strip()

            # Clean up description
            description = re.sub(r'\s+', ' ', description)
            description = description.strip('- ')

            if description and amount != 0:
                transactions.append({
                    "date": self._normalize_date(date_match),
                    "description": description.upper(),
                    "amount": amount,
                    "type": "credit" if amount > 0 else "debit",
                    "file_id": file_id,
                    "raw_text": line
                })

        return transactions

    def _parse_amount(self, amount_str: str) -> float:
        """Convert amount string to float"""
        # Remove $ and commas
        clean = amount_str.replace('$', '').replace(',', '')
        try:
            return float(clean)
        except ValueError:
            return 0.0

    def _normalize_date(self, date_str: str) -> str:
        """Convert various date formats to YYYY-MM-DD"""
        formats_to_try = [
            '%m/%d/%Y',
            '%m/%d/%y',
            '%Y-%m-%d',
            '%m-%d-%Y',
        ]

        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return date_str  # Return as-is if can't parse

    def process_pdf(self, pdf_path: str) -> Dict:
        """
        Main method to process a PDF bank statement

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary with:
            - file_id: Unique identifier for this file
            - transactions: List of parsed transactions
            - raw_text: Original extracted text
            - success: Whether parsing was successful
        """
        file_id = str(uuid.uuid4())[:8]  # Short unique ID

        try:
            # Try table extraction first (more accurate for structured PDFs)
            tables = self.extract_tables_pdfplumber(pdf_path)

            if tables:
                # If tables found, parse from tables
                transactions = self._parse_from_tables(tables, file_id)
            else:
                # Fall back to text extraction
                text = self.extract_text_pymupdf(pdf_path)
                transactions = self.parse_transactions_from_text(text, file_id)

            return {
                "file_id": file_id,
                "file_name": Path(pdf_path).name,
                "transactions": transactions,
                "transaction_count": len(transactions),
                "success": len(transactions) > 0
            }

        except Exception as e:
            return {
                "file_id": file_id,
                "file_name": Path(pdf_path).name,
                "transactions": [],
                "transaction_count": 0,
                "success": False,
                "error": str(e)
            }

    def _parse_from_tables(
        self,
        tables: List[pd.DataFrame],
        file_id: str
    ) -> List[Dict]:
        """Parse transactions from extracted tables"""
        transactions = []

        for df in tables:
            # Try to identify columns
            cols = [str(c).lower() for c in df.columns]

            date_col = self._find_column(cols, ['date', 'trans date', 'posted'])
            desc_col = self._find_column(cols, ['description', 'details', 'transaction'])
            amount_col = self._find_column(cols, ['amount', 'debit', 'credit', 'value'])

            if date_col is None or amount_col is None:
                continue

            for _, row in df.iterrows():
                try:
                    date_val = str(row.iloc[date_col]) if date_col is not None else ""
                    desc_val = str(row.iloc[desc_col]) if desc_col is not None else ""
                    amount_val = str(row.iloc[amount_col]) if amount_col is not None else "0"

                    amount = self._parse_amount(amount_val)

                    if amount != 0:
                        transactions.append({
                            "date": self._normalize_date(date_val),
                            "description": desc_val.upper(),
                            "amount": amount,
                            "type": "credit" if amount > 0 else "debit",
                            "file_id": file_id
                        })
                except Exception:
                    continue

        return transactions

    def _find_column(
        self,
        columns: List[str],
        keywords: List[str]
    ) -> Optional[int]:
        """Find column index matching any keyword"""
        for i, col in enumerate(columns):
            for keyword in keywords:
                if keyword in col:
                    return i
        return None


# ===================
# DEMO DATA LOADER
# ===================
def load_demo_data(csv_path: str, file_id: str = "demo") -> List[Dict]:
    """
    Load demo transactions from CSV file

    Args:
        csv_path: Path to the CSV file
        file_id: ID to assign to these transactions

    Returns:
        List of transaction dictionaries
    """
    df = pd.read_csv(csv_path)

    transactions = []
    for _, row in df.iterrows():
        transactions.append({
            "date": row["date"],
            "description": row["description"].upper(),
            "amount": float(row["amount"]),
            "type": row["type"],
            "file_id": file_id
        })

    return transactions


# ===================
# TEST
# ===================
if __name__ == "__main__":
    # Test with demo data
    from config import DEMO_CSV_PATH

    print("📄 Testing Demo Data Loader...")
    transactions = load_demo_data(str(DEMO_CSV_PATH))

    print(f"✓ Loaded {len(transactions)} transactions")
    print("\nSample transactions:")
    for tx in transactions[:5]:
        print(f"  {tx['date']} | {tx['description'][:30]:30} | ${tx['amount']:>10.2f}")
