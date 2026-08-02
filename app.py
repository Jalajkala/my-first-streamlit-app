import streamlit as st
import pandas as pd
from sqlalchemy import text

# Page Configuration
st.set_page_config(page_title="Finealth Dashboard", page_icon="🏦", layout="wide")

st.title("🏦 Finealth: Financial Health Tracker")

# 1. Connect to the Neon PostgreSQL Database
# (Ensure your secrets are set up in the Streamlit Cloud dashboard!)
conn = st.connection("postgresql", type="sql")

# Create tabs for organization
tab1, tab2 = st.tabs(["➕ Add New Account", "📋 View Existing Accounts"])

with tab1:
    st.subheader("Setup Financial Accounts")
    st.write("Add your checking, savings, brokerage, and cash accounts here.")
    
    # 2. Create the Data Entry Form
    with st.form("add_account_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            account_name = st.text_input("Account Name", placeholder="e.g., Kasikorn Savings, SBI NRE...")
            # Pre-populating currencies based on your background (INR, THB, EUR)
            currency = st.selectbox("Base Currency", ["INR", "THB", "EUR", "USD", "GBP"])
            
        with col2:
            account_type = st.selectbox("Account Type", ["Checking", "Savings", "Brokerage", "Cash", "Digital Wallet", "Other"])
            is_active = st.checkbox("Account is Active", value=True)
            
        submit_button = st.form_submit_button("Save Account")
        
        # 3. Handle Form Submission
        if submit_button:
            if account_name:
                # Open a database session to write data
                with conn.session as s:
                    sql = text("""
                        INSERT INTO accounts (account_name, account_type, currency, is_active) 
                        VALUES (:name, :type, :currency, :active);
                    """)
                    s.execute(sql, {
                        "name": account_name, 
                        "type": account_type, 
                        "currency": currency, 
                        "active": is_active
                    })
                    s.commit()
                st.success(f"Successfully added account: {account_name}")
            else:
                st.error("Please provide an Account Name.")

with tab2:
    st.subheader("Current Accounts Portfolio")
    
    # 4. Fetch and display the data
    # TTL=0 ensures we bypass the cache and fetch fresh data after adding a new account
    df_accounts = conn.query("SELECT * FROM accounts ORDER BY id DESC;", ttl=0)
    
    if df_accounts.empty:
        st.info("No accounts found. Go to the 'Add New Account' tab to create one.")
    else:
        st.dataframe(
            df_accounts, 
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "ID",
                "account_name": "Account Name",
                "account_type": "Category",
                "currency": "Currency",
                "is_active": "Active Status"
            }
        )
