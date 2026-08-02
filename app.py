import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date

# Page Configuration
st.set_page_config(page_title="Finealth Dashboard", page_icon="🏦", layout="wide")
st.title("🏦 Finealth: Financial Health Tracker")

# Connect to the Neon PostgreSQL Database
conn = st.connection("postgresql", type="sql")

# --- APP NAVIGATION ---
st.sidebar.title("Navigation")
menu = st.sidebar.radio("Go to module:", ["Accounts", "Assets & Liabilities", "Investments", "Baseline Snapshots"])

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
                        sql = text("INSERT INTO accounts (account_name, account_type, currency, is_active) VALUES (:name, :type, :currency, :active);")
                        s.execute(sql, {"name": account_name, "type": account_type, "currency": currency, "active": is_active})
                        s.commit()
                    st.success(f"Successfully added account: {account_name}")

    with tab2:
        df_accounts = conn.query("SELECT * FROM accounts ORDER BY id DESC;", ttl=0)
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
                is_active = st.checkbox("Active", value=True)
                
            if st.form_submit_button("Save Item"):
                if item_name:
                    with conn.session as s:
                        sql = text("INSERT INTO assets_liabilities (name, category, type, currency, is_active) VALUES (:name, :category, :type, :currency, :active);")
                        s.execute(sql, {"name": item_name, "category": category, "type": item_type, "currency": currency, "active": is_active})
                        s.commit()
                    st.success(f"Successfully added: {item_name}")

    with tab2:
        df_al = conn.query("SELECT * FROM assets_liabilities ORDER BY type ASC, id DESC;", ttl=0)
        st.dataframe(df_al, use_container_width=True, hide_index=True)

# ==========================================
# MODULE 3: INVESTMENTS
# ==========================================
elif menu == "Investments":
    st.header("📈 Investment Portfolio Master")
    tab1, tab2 = st.tabs(["➕ Add Investment", "📋 View Investments"])

    with tab1:
        df_active_accounts = conn.query("SELECT id, account_name FROM accounts WHERE is_active = true ORDER BY account_name;", ttl=0)
        account_options = {"None (Unlinked)": None}
        for _, row in df_active_accounts.iterrows():
            account_options[row['account_name']] = row['id']

        with st.form("add_investment_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                inv_name = st.text_input("Investment Name")
                inv_type = st.selectbox("Investment Type", ["Mutual Fund", "SIP", "Fixed Deposit", "Stock", "Bonds", "Other"])
            with col2:
                currency = st.selectbox("Currency", ["INR", "THB", "EUR", "USD"])
                selected_account_label = st.selectbox("Linked Funding Account", list(account_options.keys()))
                
            if st.form_submit_button("Save Investment"):
                if inv_name:
                    linked_account_id = account_options[selected_account_label]
                    with conn.session as s:
                        sql = text("INSERT INTO investments (investment_name, investment_type, linked_account_id, currency) VALUES (:name, :type, :linked_id, :currency);")
                        s.execute(sql, {"name": inv_name, "type": inv_type, "linked_id": linked_account_id, "currency": currency})
                        s.commit()
                    st.success(f"Successfully added investment: {inv_name}")

    with tab2:
        sql_view = """
            SELECT i.id, i.investment_name, i.investment_type, a.account_name AS linked_account, i.currency 
            FROM investments i LEFT JOIN accounts a ON i.linked_account_id = a.id ORDER BY i.id DESC;
        """
        st.dataframe(conn.query(sql_view, ttl=0), use_container_width=True, hide_index=True)

# ==========================================
# MODULE 4: BASELINE SNAPSHOTS
# ==========================================
elif menu == "Baseline Snapshots":
    st.header("📸 Baseline Snapshots")
    st.write("Record starting balances or point-in-time valuations to track your net worth in INR.")
    
    tab1, tab2 = st.tabs(["➕ Add Snapshot", "📋 View Snapshots"])

    with tab1:
        # 1. Step 1: Select the entity type OUTSIDE the form so it dynamically updates the next query
        entity_type = st.selectbox("What are you recording a snapshot for?", ["Account", "Asset_Liability", "Investment"])
        
        # Fetch the specific items based on the choice above
        if entity_type == "Account":
            df_entities = conn.query("SELECT id, account_name as name, currency FROM accounts WHERE is_active = true", ttl=0)
        elif entity_type == "Asset_Liability":
            df_entities = conn.query("SELECT id, name, currency FROM assets_liabilities WHERE is_active = true", ttl=0)
        else:
            df_entities = conn.query("SELECT id, investment_name as name, currency FROM investments", ttl=0)
            
        entity_options = {}
        for _, row in df_entities.iterrows():
            # Adding the currency in brackets helps you remember which FX rate to use!
            entity_options[f"{row['name']} ({row['currency']})"] = row['id']

        if not entity_options:
            st.warning(f"No active {entity_type}s found. Please add one first.")
        else:
            # 2. Step 2: The actual form
            with st.form("add_snapshot_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    snapshot_date = st.date_input("Date of Snapshot", value=date.today())
                    selected_entity_label = st.selectbox("Select Item", list(entity_options.keys()))
                    
                with col2:
                    balance = st.number_input("Balance or Value (in local currency)", min_value=0.0, format="%.2f")
                    # Emphasize the INR conversion logic we discussed earlier
                    fx_rate = st.number_input("Exchange Rate to INR (1.0 for INR items)", value=1.0000, format="%.4f")
                
                notes = st.text_input("Notes (Optional)", placeholder="e.g., Initial setup, Month-end update")
                    
                if st.form_submit_button("Save Snapshot"):
                    entity_id = entity_options[selected_entity_label]
                    
                    with conn.session as s:
                        sql = text("""
                            INSERT INTO baseline_snapshots (snapshot_date, entity_type, entity_id, balance_or_value, exchange_rate_to_inr, notes) 
                            VALUES (:date, :type, :e_id, :balance, :fx, :notes);
                        """)
                        s.execute(sql, {
                            "date": snapshot_date, 
                            "type": entity_type, 
                            "e_id": entity_id, 
                            "balance": balance,
                            "fx": fx_rate,
                            "notes": notes
                        })
                        s.commit()
                    st.success(f"Successfully recorded snapshot for {selected_entity_label}")

    with tab2:
        # A complex SQL query to combine the names from all three separate tables into one unified view
        sql_view = """
            SELECT 
                b.id, 
                b.snapshot_date, 
                b.entity_type, 
                CASE 
                    WHEN b.entity_type = 'Account' THEN a.account_name
                    WHEN b.entity_type = 'Asset_Liability' THEN al.name
                    WHEN b.entity_type = 'Investment' THEN i.investment_name
                END as entity_name,
                b.balance_or_value, 
                b.exchange_rate_to_inr,
                (b.balance_or_value * b.exchange_rate_to_inr) as value_in_inr,
                b.notes
            FROM baseline_snapshots b
            LEFT JOIN accounts a ON b.entity_type = 'Account' AND b.entity_id = a.id
            LEFT JOIN assets_liabilities al ON b.entity_type = 'Asset_Liability' AND b.entity_id = al.id
            LEFT JOIN investments i ON b.entity_type = 'Investment' AND b.entity_id = i.id
            ORDER BY b.snapshot_date DESC, b.id DESC;
        """
        df_snap = conn.query(sql_view, ttl=0)
        
        if df_snap.empty:
            st.info("No snapshots found.")
        else:
            st.dataframe(
                df_snap, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "snapshot_date": "Date",
                    "entity_type": "Category",
                    "entity_name": "Item Name",
                    "balance_or_value": st.column_config.NumberColumn("Local Value", format="%.2f"),
                    "exchange_rate_to_inr": st.column_config.NumberColumn("FX to INR", format="%.4f"),
                    "value_in_inr": st.column_config.NumberColumn("INR Equivalent", format="₹%.2f")
                }
            )
