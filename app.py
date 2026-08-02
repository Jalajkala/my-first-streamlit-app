import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date
import time
import plotly.express as px

# Page Configuration
st.set_page_config(page_title="Finealth Dashboard", page_icon="🏦", layout="wide")
st.title("🏦 Finealth: Financial Health Tracker")

# Connect to the Neon PostgreSQL Database
conn = st.connection("postgresql", type="sql")

# --- APP NAVIGATION ---
st.sidebar.title("Navigation")
# Added 'Dashboard' as the default landing page
menu = st.sidebar.radio("Go to module:", ["Dashboard", "Accounts", "Assets & Liabilities", "Investments", "Baseline Snapshots", "Transactions"])

# ==========================================
# MODULE 0: DASHBOARD
# ==========================================
if menu == "Dashboard":
    st.header("📊 Financial Health Dashboard")
    st.write("Your net worth composition based on your latest recorded snapshots.")

    # 1. Grab the Top-Level KPIs (Using your existing Latest Snapshot logic)
    sql_latest_snapshots = """
        WITH RankedSnapshots AS (
            SELECT 
                b.entity_type, 
                CASE 
                    WHEN b.entity_type = 'Account' THEN a.account_name
                    WHEN b.entity_type = 'Asset_Liability' THEN al.name
                    WHEN b.entity_type = 'Investment' THEN i.investment_name
                END as entity_name,
                b.balance_or_value,
                b.exchange_rate_to_inr,
                CASE 
                    WHEN b.entity_type = 'Asset_Liability' AND al.type = 'Liability' 
                    THEN (b.balance_or_value * b.exchange_rate_to_inr * -1)
                    ELSE (b.balance_or_value * b.exchange_rate_to_inr)
                END as value_in_inr,
                b.snapshot_date,
                ROW_NUMBER() OVER(PARTITION BY b.entity_type, b.entity_id ORDER BY b.snapshot_date DESC) as rn
            FROM baseline_snapshots b
            LEFT JOIN accounts a ON b.entity_type = 'Account' AND b.entity_id = a.id
            LEFT JOIN assets_liabilities al ON b.entity_type = 'Asset_Liability' AND b.entity_id = al.id
            LEFT JOIN investments i ON b.entity_type = 'Investment' AND b.entity_id = i.id
        )
        SELECT * FROM RankedSnapshots WHERE rn = 1;
    """
    df_snaps = conn.query(sql_latest_snapshots, ttl=0)
    
    if df_snaps.empty:
        st.info("No snapshot data available to generate the dashboard. Please add baseline snapshots first.")
    else:
        # Calculate Top Level KPIs
        total_nw = df_snaps['value_in_inr'].sum()
        total_items = len(df_snaps)
        
        current_month = date.today().replace(day=1)
        sql_tx_count = f"SELECT COUNT(*) as count FROM transactions WHERE transaction_date >= '{current_month}'"
        df_tx_count = conn.query(sql_tx_count, ttl=0)
        tx_count = df_tx_count.iloc[0]['count'] if not df_tx_count.empty else 0

        # Render KPI Cards
        st.subheader("Key Metrics")
        col1, col2, col3 = st.columns(3)
        col1.metric("Current Net Worth (INR)", f"₹ {total_nw:,.2f}")
        col2.metric("Tracked Entities", f"{total_items}")
        col3.metric("Transactions This Month", f"{tx_count}")
        
        st.divider()

        # ---------------------------------------------------------
        # NEW SECTION: Historical Net Worth Trend (Area Chart)
        # ---------------------------------------------------------
        st.subheader("Historical Net Worth Trend")
        
        # Step A: Get EVERY snapshot ever recorded, treating liabilities as negative
        sql_history = """
            SELECT 
                b.snapshot_date,
                b.entity_type || '_' || b.entity_id AS unique_entity_id,
                CASE 
                    WHEN b.entity_type = 'Asset_Liability' AND al.type = 'Liability' 
                    THEN (b.balance_or_value * b.exchange_rate_to_inr * -1)
                    ELSE (b.balance_or_value * b.exchange_rate_to_inr)
                END as value_in_inr
            FROM baseline_snapshots b
            LEFT JOIN assets_liabilities al ON b.entity_type = 'Asset_Liability' AND b.entity_id = al.id
            ORDER BY b.snapshot_date ASC;
        """
        df_all_snaps = conn.query(sql_history, ttl=0)

        if not df_all_snaps.empty:
            # Step B: Pivot the data so every date is a row, and every account is a column
            df_pivot = df_all_snaps.pivot_table(
                index='snapshot_date', 
                columns='unique_entity_id', 
                values='value_in_inr',
                aggfunc='last' # If you logged twice in one day, take the last one
            )
            
            # Step C: The Forward Fill Magic! 
            # Carry previous balances forward to dates where they weren't explicitly updated
            df_pivot = df_pivot.ffill().fillna(0)
            
            # Step D: Sum all columns horizontally to get the Total Net Worth for each date
            df_pivot['Total Net Worth'] = df_pivot.sum(axis=1)
            df_trend = df_pivot.reset_index()

            # Step E: Render the Plotly Area Chart
            import plotly.express as px
            fig = px.area(
                df_trend, 
                x='snapshot_date', 
                y='Total Net Worth', 
                color_discrete_sequence=['#00b4d8'] # A nice financial blue color
            )
            
            # Clean up the chart UI and format X-axis to Month-Year
            fig.update_layout(
                xaxis_title="", # Removed title to keep it clean, the dates speak for themselves
                yaxis_title="Net Worth (INR)",
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis_tickformat="₹,.0f", # Format the Y-axis numbers as Rupees
                xaxis=dict(
                    tickformat="%b %Y",   # Formats ticks as 'Aug 2026', 'Sep 2026', etc.
                    dtick="M1"            # Forces Plotly to place a tick mark exactly every 1 month
                )
            )
            # Fill the container completely
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # Render original bottom charts
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("Net Worth Composition")
            df_grouped = df_snaps.groupby('entity_type')['value_in_inr'].sum().reset_index()
            df_grouped['entity_type'] = df_grouped['entity_type'].replace({
                'Account': 'Liquid Accounts', 'Asset_Liability': 'Assets & Liabilities', 'Investment': 'Investments'
            })
            st.bar_chart(df_grouped, x="entity_type", y="value_in_inr")
            
        with col_chart2:
            st.subheader("Top 5 Holdings (INR)")
            df_top = df_snaps.reindex(df_snaps.value_in_inr.abs().sort_values(ascending=False).index).head(5)
            st.bar_chart(df_top, x="entity_name", y="value_in_inr")

# ==========================================
# MODULE 1: ACCOUNTS
# ==========================================
elif menu == "Accounts":
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
    
    # We now have THREE tabs
    tab1, tab2, tab3 = st.tabs(["➕ Add Item", "📋 View Portfolio", "✏️ Edit / Delete Item"])

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

    with tab3:
        st.subheader("Modify or Remove an Item")
        df_edit_al = conn.query("SELECT * FROM assets_liabilities ORDER BY name;", ttl=0)
        
        if not df_edit_al.empty:
            # Create a dictionary mapping the label to the database ID
            edit_options = {f"{row['name']} ({row['type']})": row['id'] for _, row in df_edit_al.iterrows()}
            selected_edit_label = st.selectbox("Select Item to Modify", list(edit_options.keys()))
            selected_id = edit_options[selected_edit_label]
            
            # Extract the current data for the selected item to pre-fill the form
            current_data = df_edit_al[df_edit_al['id'] == selected_id].iloc[0]
            
            with st.form("edit_al_form"):
                # A clever trick to put two distinct actions in one form
                action = st.radio("Choose Action", ["Update Record", "Delete Record"], horizontal=True)
                st.write("---")
                
                col1, col2 = st.columns(2)
                with col1:
                    new_name = st.text_input("Name", value=current_data['name'])
                    
                    types = ["Asset", "Liability"]
                    # Find the index of the current value so the radio button defaults correctly
                    new_type = st.radio("Classification ", types, index=types.index(current_data['type']), horizontal=True)
                    
                    currencies = ["INR", "THB", "EUR", "USD"]
                    new_currency = st.selectbox("Valuation Currency ", currencies, index=currencies.index(current_data['currency']))
                with col2:
                    categories = ["Real Estate", "Vehicle", "Home Loan", "Car Loan", "Personal Loan", "Jewelry", "Other"]
                    cat_idx = categories.index(current_data['category']) if current_data['category'] in categories else 0
                    new_category = st.selectbox("Category ", categories, index=cat_idx)
                    
                    new_active = st.checkbox("Active ", value=current_data['is_active'])
                
                if st.form_submit_button("Execute Action"):
                    if action == "Delete Record":
                        with conn.session as s:
                            s.execute(text("DELETE FROM assets_liabilities WHERE id = :id"), {"id": selected_id})
                            s.commit()
                        st.success(f"Deleted {current_data['name']} successfully!")
                        time.sleep(1) # Pause so you can read the success message
                        st.rerun()    # Instantly refresh the page to update the dropdowns
                        
                    elif action == "Update Record":
                        with conn.session as s:
                            sql = text("""
                                UPDATE assets_liabilities 
                                SET name=:name, category=:cat, type=:type, currency=:curr, is_active=:active
                                WHERE id=:id
                            """)
                            s.execute(sql, {
                                "name": new_name, "cat": new_category, "type": new_type, 
                                "curr": new_currency, "active": new_active, "id": selected_id
                            })
                            s.commit()
                        st.success(f"Updated {new_name} successfully!")
                        time.sleep(1)
                        st.rerun()

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
                inv_type = st.selectbox("Investment Type", ["Mutual Fund", "SIP", "Fixed Deposit", "Recurring Deposit", "Stock", "Bonds", "EPF", "PPF", "Other"])
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
    
    # We now have THREE tabs
    tab1, tab2, tab3 = st.tabs(["➕ Add Snapshot", "📋 View Snapshots", "✏️ Edit / Delete Snapshot"])

    with tab1:
        entity_type = st.selectbox("What are you recording a snapshot for?", ["Account", "Asset_Liability", "Investment"])
        
        if entity_type == "Account":
            df_entities = conn.query("SELECT id, account_name as name, currency FROM accounts WHERE is_active = true", ttl=0)
        elif entity_type == "Asset_Liability":
            df_entities = conn.query("SELECT id, name, currency FROM assets_liabilities WHERE is_active = true", ttl=0)
        else:
            df_entities = conn.query("SELECT id, investment_name as name, currency FROM investments", ttl=0)
            
        entity_options = {}
        for _, row in df_entities.iterrows():
            entity_options[f"{row['name']} ({row['currency']})"] = row['id']

        if not entity_options:
            st.warning(f"No active {entity_type}s found. Please add one first.")
        else:
            with st.form("add_snapshot_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    snapshot_date = st.date_input("Date of Snapshot", value=date.today())
                    selected_entity_label = st.selectbox("Select Item", list(entity_options.keys()))
                with col2:
                    balance = st.number_input("Balance or Value (in local currency)", min_value=0.0, format="%.2f")
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
                            "date": snapshot_date, "type": entity_type, "e_id": entity_id, 
                            "balance": balance, "fx": fx_rate, "notes": notes
                        })
                        s.commit()
                    st.success(f"Successfully recorded snapshot for {selected_entity_label}")

    with tab2:
        sql_view = """
            SELECT 
                b.id, b.snapshot_date, b.entity_type, 
                CASE 
                    WHEN b.entity_type = 'Account' THEN a.account_name
                    WHEN b.entity_type = 'Asset_Liability' THEN al.name
                    WHEN b.entity_type = 'Investment' THEN i.investment_name
                END as entity_name,
                b.balance_or_value, b.exchange_rate_to_inr,
                (b.balance_or_value * b.exchange_rate_to_inr) as value_in_inr, b.notes
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
            st.dataframe(df_snap, use_container_width=True, hide_index=True,
                column_config={
                    "snapshot_date": "Date", "entity_type": "Category", "entity_name": "Item Name",
                    "balance_or_value": st.column_config.NumberColumn("Local Value", format="%.2f"),
                    "exchange_rate_to_inr": st.column_config.NumberColumn("FX to INR", format="%.4f"),
                    "value_in_inr": st.column_config.NumberColumn("INR Equivalent", format="₹%.2f")
                }
            )
            
    with tab3:
        st.subheader("Modify or Remove a Snapshot")
        # Reuse the rich view so we can display the actual item name in the dropdown
        df_edit_snap = conn.query(sql_view, ttl=0)
        
        if not df_edit_snap.empty:
            snap_options = {f"{row['snapshot_date']} - {row['entity_name']} (ID: {row['id']})": row['id'] for _, row in df_edit_snap.iterrows()}
            selected_snap_label = st.selectbox("Select Snapshot to Modify", list(snap_options.keys()))
            selected_id = snap_options[selected_snap_label]
            
            # Re-fetch the raw data for editing
            current_data = conn.query(f"SELECT * FROM baseline_snapshots WHERE id = {selected_id}", ttl=0).iloc[0]
            
            with st.form("edit_snapshot_form"):
                action = st.radio("Choose Action", ["Update Record", "Delete Record"], horizontal=True)
                st.write(f"**Editing Snapshot for:** {selected_snap_label.split(' (')[0]}")
                
                col1, col2 = st.columns(2)
                with col1:
                    new_date = st.date_input("Date of Snapshot", value=current_data['snapshot_date'])
                    new_balance = st.number_input("Balance or Value", value=float(current_data['balance_or_value']), format="%.2f")
                with col2:
                    new_fx = st.number_input("Exchange Rate to INR", value=float(current_data['exchange_rate_to_inr']), format="%.4f")
                    new_notes = st.text_input("Notes", value=current_data['notes'] if current_data['notes'] else "")
                    
                if st.form_submit_button("Execute Action"):
                    if action == "Delete Record":
                        with conn.session as s:
                            s.execute(text("DELETE FROM baseline_snapshots WHERE id = :id"), {"id": selected_id})
                            s.commit()
                        st.success("Snapshot deleted successfully!")
                        time.sleep(1)
                        st.rerun()
                        
                    elif action == "Update Record":
                        with conn.session as s:
                            sql = text("""
                                UPDATE baseline_snapshots 
                                SET snapshot_date=:date, balance_or_value=:bal, exchange_rate_to_inr=:fx, notes=:notes
                                WHERE id=:id
                            """)
                            s.execute(sql, {
                                "date": new_date, "bal": new_balance, "fx": new_fx, 
                                "notes": new_notes, "id": selected_id
                            })
                            s.commit()
                        st.success("Snapshot updated successfully!")
                        time.sleep(1)
                        st.rerun()

# ==========================================
# MODULE 5: TRANSACTIONS
# ==========================================
elif menu == "Transactions":
    st.header("💸 Transaction Ledger")
    st.write("Log income, expenses, and international transfers across your accounts.")
    
    tab1, tab2 = st.tabs(["➕ Add Transaction", "📋 View Ledger"])

    with tab1:
        transaction_type = st.selectbox("Transaction Type", ["Transfer", "Income", "Expense", "Investment_Buy", "Loan_Repayment"])
        
        df_active_accounts = conn.query("SELECT id, account_name, currency FROM accounts WHERE is_active = true ORDER BY account_name;", ttl=0)
        account_options = {"None": None}
        for _, row in df_active_accounts.iterrows():
            account_options[f"{row['account_name']} ({row['currency']})"] = row['id']

        with st.form("add_transaction_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                transaction_date = st.date_input("Date", value=date.today())
                category = st.text_input("Category / Tag", placeholder="e.g., Salary, Rent, SIP Installment, Remittance")
                
                if transaction_type in ["Transfer", "Expense", "Investment_Buy", "Loan_Repayment"]:
                    from_account_label = st.selectbox("From Account", list(account_options.keys()))
                    amount_sent = st.number_input("Amount Sent (Local Currency)", min_value=0.0, format="%.2f")
                else:
                    from_account_label = "None"
                    amount_sent = None

            with col2:
                notes = st.text_input("Notes", placeholder="Optional reference")
                
                if transaction_type in ["Transfer", "Income"]:
                    to_account_label = st.selectbox("To Account", list(account_options.keys()))
                    amount_received = st.number_input("Amount Received (Local Currency)", min_value=0.0, format="%.2f")
                else:
                    to_account_label = "None"
                    amount_received = None

            if st.form_submit_button("Save Transaction"):
                from_acc_id = account_options[from_account_label] if from_account_label != "None" else None
                to_acc_id = account_options[to_account_label] if to_account_label != "None" else None
                
                with conn.session as s:
                    sql = text("""
                        INSERT INTO transactions 
                        (transaction_date, transaction_type, from_account_id, to_account_id, amount_sent, amount_received, category, notes) 
                        VALUES (:date, :type, :from_id, :to_id, :sent, :received, :category, :notes);
                    """)
                    s.execute(sql, {
                        "date": transaction_date, "type": transaction_type, 
                        "from_id": from_acc_id, "to_id": to_acc_id, 
                        "sent": amount_sent, "received": amount_received, 
                        "category": category, "notes": notes
                    })
                    s.commit()
                st.success("Successfully logged transaction!")

    with tab2:
        sql_view = """
            SELECT 
                t.id, t.transaction_date, t.transaction_type, 
                f.account_name AS from_account, t.amount_sent, 
                to_acc.account_name AS to_account, t.amount_received, 
                t.category, t.notes 
            FROM transactions t
            LEFT JOIN accounts f ON t.from_account_id = f.id
            LEFT JOIN accounts to_acc ON t.to_account_id = to_acc.id
            ORDER BY t.transaction_date DESC, t.id DESC;
        """
        df_tx = conn.query(sql_view, ttl=0)
        
        if df_tx.empty:
            st.info("No transactions found.")
        else:
            st.dataframe(
                df_tx, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "transaction_date": "Date",
                    "transaction_type": "Type",
                    "from_account": "From",
                    "amount_sent": st.column_config.NumberColumn("Sent", format="%.2f"),
                    "to_account": "To",
                    "amount_received": st.column_config.NumberColumn("Received", format="%.2f"),
                    "category": "Category"
                }
            )
