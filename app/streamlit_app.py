"""
STREAMLIT_APP.PY - Finance Advisor Agent UI

Features:
- Demo Mode: Use sample CSV data for testing
- Real Mode: Upload PDF bank statements
- Monthly income input (AI remembers)
- File management with delete (syncs with vector DB)
- Chat interface for financial queries

Run with: streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import streamlit as st
import tempfile
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import (
    GROQ_API_KEY, GROQ_MODEL,
    QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
    DEMO_CSV_PATH, CATEGORIES_PATH,
    USER_PROFILE_PATH, validate_config
)
from pdf_processor import PDFProcessor, load_demo_data
from categorizer import TransactionCategorizer
from vector_store import FinanceVectorStore
from query_engine import FinanceQueryEngine
from user_profile import UserProfile


# ===================
# PAGE CONFIG
# ===================
st.set_page_config(
    page_title="Finance Advisor AI",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ===================
# INITIALIZE COMPONENTS
# ===================
@st.cache_resource
def init_components():
    """Initialize all components (cached for performance)"""
    # Check config
    if not GROQ_API_KEY:
        return None, None, None, None, "GROQ_API_KEY not set"

    if not QDRANT_URL or not QDRANT_API_KEY:
        return None, None, None, None, "QDRANT_URL or QDRANT_API_KEY not set"

    try:
        # Initialize categorizer
        categorizer = TransactionCategorizer(str(CATEGORIES_PATH))

        # Initialize vector store (Qdrant Cloud)
        vector_store = FinanceVectorStore(
            qdrant_url=QDRANT_URL,
            qdrant_api_key=QDRANT_API_KEY,
            collection_name=QDRANT_COLLECTION
        )

        # Initialize user profile
        user_profile = UserProfile(str(USER_PROFILE_PATH))

        # Initialize query engine with vector store that has loaded index
        query_engine = FinanceQueryEngine(
            vector_store=vector_store,
            groq_api_key=GROQ_API_KEY,
            model=GROQ_MODEL,
            monthly_income=user_profile.get_monthly_income()
        )

        # Debug: Print init status
        print(f"[INIT] Vector store index loaded: {vector_store.index is not None}")
        print(f"[INIT] Stats: {vector_store.get_collection_stats()}")

        return categorizer, vector_store, query_engine, user_profile, None

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None, None, None, str(e)


def get_components():
    """Get or initialize components"""
    categorizer, vector_store, query_engine, user_profile, error = init_components()

    if error:
        st.error(f"Initialization Error: {error}")
        st.info("Please check your .env file and ensure GROQ_API_KEY, QDRANT_URL, and QDRANT_API_KEY are set.")
        st.stop()

    return categorizer, vector_store, query_engine, user_profile


# ===================
# SIDEBAR
# ===================
def render_sidebar():
    """Render sidebar with settings and file management"""
    categorizer, vector_store, query_engine, user_profile = get_components()

    st.sidebar.title("Settings")

    # Mode Toggle
    st.sidebar.subheader("Mode")
    mode = st.sidebar.radio(
        "Select Mode",
        ["Demo Mode", "Real Mode"],
        help="Demo: Use sample data | Real: Upload your PDF statements"
    )

    st.sidebar.divider()

    # Monthly Income
    st.sidebar.subheader("Monthly Income")
    current_income = user_profile.get_monthly_income()

    new_income = st.sidebar.number_input(
        "Enter your monthly income ($)",
        min_value=0.0,
        max_value=1000000.0,
        value=float(current_income),
        step=100.0,
        help="AI will use this to calculate spending percentages"
    )

    if new_income != current_income:
        user_profile.set_monthly_income(new_income)
        query_engine.update_income(new_income)
        st.sidebar.success(f"Income updated to ${new_income:,.2f}")

    st.sidebar.divider()

    # File Management
    st.sidebar.subheader("Uploaded Files")

    files = user_profile.get_files()
    if files:
        for file_info in files:
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                st.text(f"{file_info['filename'][:20]}...")
                st.caption(f"{file_info['transaction_count']} transactions")
            with col2:
                if st.button("X", key=f"del_{file_info['file_id']}", help="Delete file"):
                    # Delete from vector store
                    vector_store.delete_by_file_id(file_info['file_id'])
                    # Delete from profile
                    user_profile.remove_file(file_info['file_id'])
                    st.rerun()
    else:
        st.sidebar.info("No files uploaded yet")

    # Stats
    st.sidebar.divider()
    st.sidebar.subheader("Statistics")
    stats = vector_store.get_collection_stats()
    st.sidebar.metric("Total Transactions", stats.get("total_points", 0))
    st.sidebar.metric("Files Uploaded", len(files))

    return mode


# ===================
# DEMO MODE
# ===================
def render_demo_mode():
    """Render demo mode interface"""
    categorizer, vector_store, query_engine, user_profile = get_components()

    st.header("Demo Mode")
    st.info("Using sample transaction data to demonstrate the Finance Advisor.")

    col1, col2 = st.columns([2, 1])

    with col1:
        if st.button("Load Demo Data", type="primary", use_container_width=True):
            with st.spinner("Loading demo transactions..."):
                # Clear existing demo data
                vector_store.delete_by_file_id("demo")
                user_profile.remove_file("demo")

                # Load and categorize demo data
                transactions = load_demo_data(str(DEMO_CSV_PATH), file_id="demo")
                categorized = categorizer.categorize_transactions(transactions)

                # Add to vector store
                added = vector_store.add_transactions(categorized)

                # Track in profile
                user_profile.add_file("demo", "sample_transactions.csv", added)

                st.success(f"Loaded {added} demo transactions!")
                st.rerun()

    with col2:
        if st.button("Clear Demo Data", use_container_width=True):
            vector_store.delete_by_file_id("demo")
            user_profile.remove_file("demo")
            st.success("Demo data cleared!")
            st.rerun()

    # Show spending analysis charts
    st.subheader("Spending Analysis")

    try:
        df = pd.read_csv(DEMO_CSV_PATH)

        # Calculate spending by category
        # Filter only expenses (negative amounts)
        expenses = df[df['amount'] < 0].copy()
        expenses['amount'] = expenses['amount'].abs()

        # Group by category (use description keywords to categorize)
        categorizer = TransactionCategorizer(str(CATEGORIES_PATH))
        categorized_list = categorizer.categorize_transactions(expenses.to_dict('records'))
        cat_df = pd.DataFrame(categorized_list)

        # Aggregate by category
        spending_by_cat = cat_df.groupby('category')['amount'].sum().reset_index()
        spending_by_cat = spending_by_cat.sort_values('amount', ascending=False)

        # Create two columns for charts
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            # Pie chart
            fig_pie = px.pie(
                spending_by_cat,
                values='amount',
                names='category',
                title='Spending by Category',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig_pie, use_container_width=True)

        with chart_col2:
            # Bar chart
            fig_bar = px.bar(
                spending_by_cat,
                x='category',
                y='amount',
                title='Spending Amount by Category',
                color='amount',
                color_continuous_scale='Reds'
            )
            fig_bar.update_layout(
                xaxis_tickangle=-45,
                height=400,
                showlegend=False
            )
            fig_bar.update_traces(texttemplate='$%{y:.0f}', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

        # Summary metrics
        st.subheader("Summary")
        metric_cols = st.columns(4)
        total_spent = expenses['amount'].sum()
        total_income = df[df['amount'] > 0]['amount'].sum()
        num_transactions = len(df)
        top_category = spending_by_cat.iloc[0]['category'] if len(spending_by_cat) > 0 else "N/A"

        metric_cols[0].metric("Total Spent", f"${total_spent:,.2f}")
        metric_cols[1].metric("Total Income", f"${total_income:,.2f}")
        metric_cols[2].metric("Transactions", num_transactions)
        metric_cols[3].metric("Top Category", top_category.title())

        # Show transactions table
        with st.expander("View All Transactions"):
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.warning(f"Could not load data: {e}")


# ===================
# REAL MODE
# ===================
def render_real_mode():
    """Render real mode interface for PDF uploads"""
    categorizer, vector_store, query_engine, user_profile = get_components()

    st.header("Real Mode")
    st.info("Upload your bank statement PDFs to get personalized financial advice.")

    # File Upload
    uploaded_file = st.file_uploader(
        "Upload Bank Statement (PDF)",
        type=["pdf"],
        help="Upload a PDF bank statement to analyze"
    )

    if uploaded_file:
        if st.button("Process PDF", type="primary"):
            with st.spinner("Extracting transactions from PDF..."):
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                try:
                    # Process PDF
                    processor = PDFProcessor()
                    result = processor.process_pdf(tmp_path)

                    if result["success"]:
                        # Categorize transactions
                        categorized = categorizer.categorize_transactions(
                            result["transactions"]
                        )

                        # Add to vector store
                        added = vector_store.add_transactions(categorized)

                        # Track in profile
                        user_profile.add_file(
                            result["file_id"],
                            uploaded_file.name,
                            added
                        )

                        st.success(f"Extracted {added} transactions from {uploaded_file.name}")

                        # Show preview
                        st.subheader("Extracted Transactions")
                        import pandas as pd
                        df = pd.DataFrame(result["transactions"][:10])
                        st.dataframe(df, use_container_width=True)

                    else:
                        st.error(f"Failed to extract transactions: {result.get('error', 'Unknown error')}")
                        st.info("Tip: Make sure the PDF contains readable transaction tables.")

                finally:
                    # Cleanup temp file
                    os.unlink(tmp_path)

    # Instructions
    with st.expander("PDF Processing Tips"):
        st.markdown("""
        **Supported Formats:**
        - Standard bank statement PDFs with transaction tables
        - Credit card statements
        - Digital statements (not scanned images)

        **Best Results:**
        - Use digital PDFs (not scanned)
        - Ensure tables have Date, Description, and Amount columns
        - Avoid password-protected PDFs

        **Troubleshooting:**
        - If extraction fails, try a different statement format
        - Some banks use complex layouts that may need custom parsing
        """)


# ===================
# CHAT INTERFACE
# ===================
def render_chat():
    """Render chat interface - chat style with input at bottom"""
    categorizer, vector_store, query_engine, user_profile = get_components()

    # Check if data is loaded
    stats = vector_store.get_collection_stats()
    total_points = stats.get("total_points", 0)

    if total_points == 0:
        st.warning("No transaction data loaded yet.")
        st.info("Go to the **Data Management** tab and click **Load Demo Data** to get started!")
        return

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Handle pending question from quick buttons
    if "pending_question" in st.session_state:
        pending = st.session_state.pending_question
        del st.session_state.pending_question
        st.session_state.messages.append({"role": "user", "content": pending})

    # Process unanswered message first (before displaying)
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        last_question = st.session_state.messages[-1]["content"]

        try:
            # Ensure index is loaded
            if vector_store.index is None:
                vector_store.index = vector_store._load_existing_index()

            # Get response
            result = query_engine.query(last_question)
            response = result["answer"]

            # Fix: Escape dollar signs to prevent LaTeX rendering issues
            response = response.replace("$", "\\$")

            # Only show transaction count for actual financial questions (not greetings)
            greeting_words = ["hello", "hi", "hey", "good morning", "good evening", "who created", "who made", "who built"]
            is_greeting = any(word in last_question.lower() for word in greeting_words)

            if not is_greeting and result.get("transactions_used", 0) > 0:
                total_in_db = vector_store.get_collection_stats().get("total_points", 0)
                response += f"\n\n---\n*Analyzed {result['transactions_used']} of {total_in_db} transactions*"

            st.session_state.messages.append({"role": "assistant", "content": response})

        except Exception as e:
            error_msg = f"I had trouble processing that. Please try again."
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

    # Top bar with status and clear button
    col1, col2 = st.columns([4, 1])
    with col1:
        income = user_profile.get_monthly_income()
        st.caption(f"💰 {total_points} transactions | Income: ${income:,.0f}/month")
    with col2:
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    st.divider()

    # Chat messages container with scrollable area
    chat_container = st.container(height=450)

    with chat_container:
        if not st.session_state.messages:
            # Welcome message
            st.markdown("""
            ### Welcome! I'm your Finance Advisor AI.

            Ask me anything about your spending, like:
            - "How much did I spend on food?"
            - "What are my biggest expenses?"
            - "Can I afford a $200 purchase?"

            Type your question below to get started!
            """)
        else:
            # Display all messages
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

    # Chat input at the bottom (this naturally stays at bottom)
    if prompt := st.chat_input("Ask about your finances..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()


# ===================
# MAIN APP
# ===================
def main():
    """Main application"""
    st.title("Finance Advisor AI")
    st.caption("Your personal AI-powered financial assistant")

    # Render sidebar and get mode
    mode = render_sidebar()

    # Main content tabs - Chat first as default
    tab_chat, tab_data = st.tabs(["Chat", "Data Management"])

    with tab_chat:
        render_chat()

    with tab_data:
        if mode == "Demo Mode":
            render_demo_mode()
        else:
            render_real_mode()

    # Footer
    st.divider()
    st.caption("Created by **Saikrishna**")


if __name__ == "__main__":
    main()
