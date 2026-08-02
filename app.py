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
menu = st.sidebar.radio("Go to module:", ["Accounts", "Assets & Liabilities"])

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
    st.write("Track physical assets, real estate, vehicles, and outstanding debts.")
    
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
                        s.execute(sql, {
                            "name": item_name, 
                            "category": category,
                            "type": item_type, 
                            "currency": currency, 
                            "active": is_active
                        })
                        s.commit()
                    st.success(f"Successfully added: {item_name}")
                else:
                    st.error("Please provide a Name.")

    with tab2:
        # Fetching data and ordering by Asset/Liability type first to group them nicely
        df_al = conn.query("SELECT * FROM assets_liabilities ORDER BY type ASC, id DESC;", ttl=0)
        
        if df_al.empty:
            st.info("No items found. Go to the 'Add Item' tab to create one.")
        else:
            st.dataframe(
                df_al, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": "ID",
                    "name": "Item Name",
                    "category": "Category",
                    "type": "Asset / Liability",
                    "currency": "Currency",
                    "is_active": "Active Status"
                }
            )
