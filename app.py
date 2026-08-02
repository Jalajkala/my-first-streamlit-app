import streamlit as st
import pandas as pd
from sqlalchemy import text

# Page Configuration
st.set_page_config(page_title="Finealth Dashboard", page_icon="🏦", layout="wide")
st.title("🏦 Finealth: Financial Health Tracker")

# Connect to the Neon PostgreSQL Database
conn = st.connection("postgresql", type="sql")

# --- APP NAVIGATION ---
st.sidebar.title("Navigation")
# Added 'Investments' to the menu
menu = st.sidebar.radio("Go to module:", ["Accounts", "Assets & Liabilities", "Investments"])

# ==========================================
# MODULE 1: ACCOUNTS
# ==========================================
if menu == "Accounts":
    st.header("🏦 Bank & Liquid Accounts")
    tab1, tab2 = st.tabs(["➕ Add New Account", "📋 View Existing Accounts"])

    with tab1:
        with st.form("add_account_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                account_name = st.text_input("Account Name", placeholder="e.g., Kasikorn Savings, SBI NRE...")
                currency = st.selectbox("Base Currency", ["INR", "THB", "EUR", "USD", "GBP"])
            with col2:
                account_type = st.selectbox("Account Type", ["Checking", "Savings", "Brokerage", "Cash", "Digital Wallet", "Other"])
                is_active = st.checkbox("Account is Active", value=True)
                
            if st.form_submit_button("Save Account"):
                if account_name:
                    with conn.session as s:
                        sql = text("""
                            INSERT INTO accounts (account_name, account_type, currency, is_active) 
                            VALUES (:name, :type, :currency, :active);
                        """)
                        s.execute(sql, {"name": account_name, "type": account_type, "currency": currency, "active": is_active})
                        s.commit()
                    st.success(f"Successfully added account: {account_name}")
                else:
                    st.error("Please provide an Account Name.")

    with tab2:
        df_accounts = conn.query("SELECT * FROM accounts ORDER BY id DESC;", ttl=0)
        if df_accounts.empty:
            st.info("No accounts found.")
        else:
            st.dataframe(df_accounts, use_container_width=True, hide_index=True)

# ==========================================
# MODULE 2: ASSETS & LIABILITIES
# ==========================================
elif menu == "Assets & Liabilities":
    st.header("🏠 Assets & Liabilities")
    
    tab1, tab2 = st.tabs(["➕ Add Item", "📋 View Portfolio"])

    with tab1:
        with st.form("add_asset_liability_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                item_name = st.text_input("Name", placeholder="e.g., Tata Punch EV, Rohan Saroha Apartment, Personal Loan")
                item_type = st.radio("Classification", ["Asset", "Liability"], horizontal=True)
                currency = st.selectbox("Valuation Currency", ["INR", "THB", "EUR", "USD"])
            with col2:
                category = st.selectbox("Category", ["Real Estate", "Vehicle", "Home Loan", "Personal Loan", "Jewelry", "Other"])
                is_active = st.checkbox("Active (Not sold or fully paid off)", value=True)
                
            if st.form_submit_button("Save Item"):
                if item_name:
                    with conn.session as s:
                        sql = text("""
                            INSERT INTO assets_liabilities (name, category, type, currency, is_active) 
                            VALUES (:name, :category, :type, :currency, :active);
                        """)
                        s.execute(sql, {"name": item_name, "category": category, "type": item_type, "currency": currency, "active": is_active})
                        s.commit()
                    st.success(f"Successfully added: {item_name}")
                else:
                    st.error("Please provide a Name.")

    with tab2:
        df_al = conn.query("SELECT * FROM assets_liabilities ORDER BY type ASC, id DESC;", ttl=0)
        if df_al.empty:
            st.info("No items found.")
        else:
            st.dataframe(df_al, use_container_width=True, hide_index=True)

# ==========================================
# MODULE 3: INVESTMENTS
# ==========================================
elif menu == "Investments":
    st.header("📈 Investment Portfolio Master")
    st.write("Track your Mutual Funds, Systematic Investment Plans (SIPs), Fixed Deposits, and other vehicles.")
    
    tab1, tab2 = st.tabs(["➕ Add Investment", "📋 View Investments"])

    with tab1:
        # 1. Fetch active accounts to populate the dropdown
        df_active_accounts = conn.query("SELECT id, account_name FROM accounts WHERE is_active = true ORDER BY account_name;", ttl=0)
        
        # Create a dictionary mapping the display name to the database ID
        account_options = {"None (Unlinked)": None}
        for _, row in df_active_accounts.iterrows():
            account_options[f"{row['account_name']}"] = row['id']

        with st.form("add_investment_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                inv_name = st.text_input("Investment Name", placeholder="e.g., Nippon India Small Cap, HDFC FD...")
                inv_type = st.selectbox("Investment Type", ["Mutual Fund", "SIP", "Fixed Deposit", "Stock", "Bonds", "Provident Fund", "Other"])
                
            with col2:
                currency = st.selectbox("Currency", ["INR", "THB", "EUR", "USD"])
                # 2. Display the dropdown using the dictionary keys
                selected_account_label = st.selectbox("Linked Funding Account", list(account_options.keys()))
                
            if st.form_submit_button("Save Investment"):
                if inv_name:
                    # Get the actual ID from the dictionary based on what the user selected
                    linked_account_id = account_options[selected_account_label]
                    
                    with conn.session as s:
                        sql = text("""
                            INSERT INTO investments (investment_name, investment_type, linked_account_id, currency) 
                            VALUES (:name, :type, :linked_id, :currency);
                        """)
                        s.execute(sql, {
                            "name": inv_name, 
                            "type": inv_type, 
                            "linked_id": linked_account_id, 
                            "currency": currency
                        })
                        s.commit()
                    st.success(f"Successfully added investment: {inv_name}")
                else:
                    st.error("Please provide an Investment Name.")

    with tab2:
        # 3. Use a SQL JOIN to replace the linked_account_id with the actual Account Name for the view
        sql_view = """
            SELECT 
                i.id, 
                i.investment_name, 
                i.investment_type, 
                a.account_name AS linked_account, 
                i.currency 
            FROM investments i
            LEFT JOIN accounts a ON i.linked_account_id = a.id
            ORDER BY i.id DESC;
        """
        df_inv = conn.query(sql_view, ttl=0)
        
        if df_inv.empty:
            st.info("No investments found. Go to the 'Add Investment' tab to create one.")
        else:
            st.dataframe(
                df_inv, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": "ID",
                    "investment_name": "Investment Name",
                    "investment_type": "Type",
                    "linked_account": "Linked Account",
                    "currency": "Currency"
                }
            )
