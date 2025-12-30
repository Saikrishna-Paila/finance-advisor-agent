"""
USER_PROFILE.PY - Manage user settings and uploaded files

This module handles:
1. Storing monthly income (AI remembers)
2. Tracking uploaded files (file_id -> filename)
3. Persisting to JSON file
4. Loading on startup

HOW IT WORKS:
=============

User uploads "November_Statement.pdf"
    -> Stored: {"file_id": "abc123", "filename": "November_Statement.pdf"}

User sets income to $5000
    -> Stored: {"monthly_income": 5000}

On restart, all settings are loaded from user_profile.json
"""

import json
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime


class UserProfile:
    """
    Manage user profile and uploaded files

    Features:
    - Persistent income storage
    - File tracking with metadata
    - JSON-based storage
    """

    def __init__(self, profile_path: str):
        """
        Initialize user profile

        Args:
            profile_path: Path to user_profile.json
        """
        self.profile_path = Path(profile_path)
        self.profile = self._load_profile()

    def _load_profile(self) -> Dict:
        """Load profile from JSON file"""
        if self.profile_path.exists():
            try:
                with open(self.profile_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass

        # Default profile
        return {
            "monthly_income": 0,
            "uploaded_files": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    def _save_profile(self):
        """Save profile to JSON file"""
        self.profile["updated_at"] = datetime.now().isoformat()

        # Ensure directory exists
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.profile_path, 'w') as f:
            json.dump(self.profile, f, indent=2)

    # ===================
    # INCOME MANAGEMENT
    # ===================

    def get_monthly_income(self) -> float:
        """Get user's monthly income"""
        return self.profile.get("monthly_income", 0)

    def set_monthly_income(self, income: float):
        """
        Set user's monthly income

        Args:
            income: Monthly income amount
        """
        self.profile["monthly_income"] = income
        self._save_profile()
        print(f"Updated monthly income to ${income:,.2f}")

    # ===================
    # FILE MANAGEMENT
    # ===================

    def add_file(
        self,
        file_id: str,
        filename: str,
        transaction_count: int = 0
    ) -> Dict:
        """
        Track an uploaded file

        Args:
            file_id: Unique ID from PDF processor
            filename: Original filename
            transaction_count: Number of transactions extracted

        Returns:
            File info dictionary
        """
        file_info = {
            "file_id": file_id,
            "filename": filename,
            "transaction_count": transaction_count,
            "uploaded_at": datetime.now().isoformat()
        }

        # Avoid duplicates
        self.profile["uploaded_files"] = [
            f for f in self.profile.get("uploaded_files", [])
            if f["file_id"] != file_id
        ]

        self.profile["uploaded_files"].append(file_info)
        self._save_profile()

        return file_info

    def remove_file(self, file_id: str) -> bool:
        """
        Remove a file from tracking

        Args:
            file_id: ID of file to remove

        Returns:
            True if file was found and removed
        """
        original_count = len(self.profile.get("uploaded_files", []))

        self.profile["uploaded_files"] = [
            f for f in self.profile.get("uploaded_files", [])
            if f["file_id"] != file_id
        ]

        removed = len(self.profile["uploaded_files"]) < original_count

        if removed:
            self._save_profile()

        return removed

    def get_files(self) -> List[Dict]:
        """Get list of all uploaded files"""
        return self.profile.get("uploaded_files", [])

    def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file info by file_id"""
        for f in self.profile.get("uploaded_files", []):
            if f["file_id"] == file_id:
                return f
        return None

    def get_total_transactions(self) -> int:
        """Get total transaction count across all files"""
        return sum(
            f.get("transaction_count", 0)
            for f in self.profile.get("uploaded_files", [])
        )

    # ===================
    # PROFILE SUMMARY
    # ===================

    def get_summary(self) -> Dict:
        """Get profile summary"""
        files = self.get_files()
        return {
            "monthly_income": self.get_monthly_income(),
            "file_count": len(files),
            "total_transactions": self.get_total_transactions(),
            "files": files
        }

    def clear_all_files(self):
        """Remove all tracked files"""
        self.profile["uploaded_files"] = []
        self._save_profile()

    def reset_profile(self):
        """Reset profile to defaults"""
        self.profile = {
            "monthly_income": 0,
            "uploaded_files": [],
            "created_at": self.profile.get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat()
        }
        self._save_profile()


# ===================
# TEST
# ===================
if __name__ == "__main__":
    from config import USER_PROFILE_PATH

    print("Testing User Profile...")

    # Initialize profile
    profile = UserProfile(str(USER_PROFILE_PATH))

    # Test income
    profile.set_monthly_income(5000)
    print(f"Monthly income: ${profile.get_monthly_income():,.2f}")

    # Test file tracking
    profile.add_file("demo", "sample_transactions.csv", 60)
    profile.add_file("test123", "November_Statement.pdf", 45)

    print(f"\nUploaded files:")
    for f in profile.get_files():
        print(f"  - {f['filename']} ({f['transaction_count']} transactions)")

    # Test removal
    profile.remove_file("test123")
    print(f"\nAfter removal: {len(profile.get_files())} files")

    # Summary
    print(f"\nProfile summary: {profile.get_summary()}")
