import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date
import time
import altair as alt
import plotly.express as px

# 1. PAGE CONFIG MUST BE THE VERY FIRST STREAMLIT COMMAND
st.set_page_config(page_title="Finealth Dashboard", page_icon="🏦", layout="wide")


# INDIAN CURRENCY FORMATTER FUNCTION

def format_inr(amount):
    """Converts a numeric value into the Indian numbering format (e.g., ₹12,34,567.89)"""
    if pd.isna(amount):
        return "₹0.00"
    
    sign = "-" if amount < 0 else ""
    val_str = f"{abs(amount):.2f}"
    int_part, dec_part = val_str.split(".")
    
    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last_three = int_part[-3:]
        remaining = int_part[:-3]
        
        chunks = []
        while len(remaining) > 2:
            chunks.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            chunks.insert(0, remaining)
            
        formatted_int = ",".join(chunks) + "," + last_three
        
    return f"₹{sign}{formatted_int}.{dec_part}"

# 2. DEFINE THE AUTHENTICATION FUNCTION
def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password_input"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            # Delete the password from session state for security
            del st.session_state["password_input"]  
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.title("🔒 Finealth Login")
        st.text_input(
            "Please enter your password", 
            type="password", 
            on_change=password_entered, 
            key="password_input"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.title("🔒 Finealth Login")
        st.text_input(
            "Please enter your password", 
            type="password", 
            on_change=password_entered, 
            key="password_input"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True


# 3. WRAP THE ENTIRE APP IN THE PASSWORD CHECK
if check_password():
    
    # --- EVERYTHING BELOW THIS LINE IS YOUR EXISTING APP CODE ---
    
    st.title("🏦 Finealth: Financial Health Tracker")

    # Connect to the Neon PostgreSQL Database
    conn = st.connection("postgresql", type="sql")

    # --- APP NAVIGATION ---
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio("Go to module:", [
        "Dashboard", 
        "Accounts", 
        "Assets & Liabilities", 
        "Investments", 
        "Baseline Snapshots", 
        "Transactions",
        "Financial Goals" # <-- Add this new option
    ])

    # Add a logout button to the bottom of the sidebar
    st.sidebar.divider()
    if st.sidebar.button("Log Out"):
        st.session_state["password_correct"] = False
        st.rerun()

# ==========================================
# MODULE 0: DASHBOARD
# ==========================================
if menu == "Dashboard":
    
    # --- ADD THIS NEW CSS BLOCK ---
    st.markdown("""
        <style>
        /* Shrink the main metric numbers */
        [data-testid="stMetricValue"] {
            font-size: 1.3rem !important;
            word-wrap: break-word !important;
        }
        /* Shrink the smaller delta (percentage) numbers */
        [data-testid="stMetricDelta"] {
            font-size: 0.9rem !important;
        }
        /* Shrink the metric labels */
        [data-testid="stMetricLabel"] {
            font-size: 0.85rem !important;
        }
        </style>
    """, unsafe_allow_html=True)
    # ------------------------------

    st.header("📊 Financial Health Dashboard")
    st.write("Your net worth composition based strictly on snapshots from the most recently recorded month.")

    # 1. Grab the Top-Level Latest Snapshots
    sql_latest_snapshots = """
        WITH MaxMonth AS (
            SELECT DATE_TRUNC('month', MAX(snapshot_date)) as max_month 
            FROM baseline_snapshots
        ),
        RankedSnapshots AS (
            SELECT 
                b.entity_type, 
                CASE 
                    WHEN b.entity_type = 'Account' THEN a.account_name
                    WHEN b.entity_type = 'Asset_Liability' THEN al.name
                    WHEN b.entity_type = 'Investment' THEN i.investment_name
                END as entity_name,
                CASE 
                    WHEN b.entity_type = 'Account' THEN a.account_type
                    WHEN b.entity_type = 'Asset_Liability' THEN al.category
                    WHEN b.entity_type = 'Investment' THEN i.investment_type
                END as detailed_category,
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
            CROSS JOIN MaxMonth
            LEFT JOIN accounts a ON b.entity_type = 'Account' AND b.entity_id = a.id
            LEFT JOIN assets_liabilities al ON b.entity_type = 'Asset_Liability' AND b.entity_id = al.id
            LEFT JOIN investments i ON b.entity_type = 'Investment' AND b.entity_id = i.id
            WHERE DATE_TRUNC('month', b.snapshot_date) = MaxMonth.max_month
        )
        SELECT * FROM RankedSnapshots WHERE rn = 1;
    """
    df_snaps = conn.query(sql_latest_snapshots, ttl=0)
    
    # 2. Grab ALL Historical Data (Moved to the top for KPI calculations)
    sql_history = """
        SELECT 
            b.snapshot_date,
            b.entity_type || '_' || b.entity_id AS unique_entity_id,
            CASE 
                WHEN b.entity_type = 'Account' THEN a.account_name
                WHEN b.entity_type = 'Asset_Liability' THEN al.name
                WHEN b.entity_type = 'Investment' THEN i.investment_name
            END as entity_name,
            CASE 
                WHEN b.entity_type = 'Account' THEN a.account_type
                WHEN b.entity_type = 'Asset_Liability' THEN al.category
                WHEN b.entity_type = 'Investment' THEN i.investment_type
            END as detailed_category,
            CASE 
                WHEN b.entity_type = 'Asset_Liability' AND al.type = 'Liability' 
                THEN (b.balance_or_value * b.exchange_rate_to_inr * -1)
                ELSE (b.balance_or_value * b.exchange_rate_to_inr)
            END as value_in_inr
        FROM baseline_snapshots b
        LEFT JOIN accounts a ON b.entity_type = 'Account' AND b.entity_id = a.id
        LEFT JOIN assets_liabilities al ON b.entity_type = 'Asset_Liability' AND b.entity_id = al.id
        LEFT JOIN investments i ON b.entity_type = 'Investment' AND b.entity_id = i.id
        ORDER BY b.snapshot_date ASC;
    """
    df_all_snaps = conn.query(sql_history, ttl=0)
    
    if df_snaps.empty:
        st.info("No snapshot data available to generate the dashboard. Please add baseline snapshots first.")
    else:
        # Calculate Base Values for Current Month
        latest_month_display = pd.to_datetime(df_snaps['snapshot_date'].iloc[0]).strftime('%b %Y')
        total_nw = df_snaps['value_in_inr'].sum()
        current_assets = df_snaps[df_snaps['value_in_inr'] > 0]['value_in_inr'].sum()
        current_liabilities = df_snaps[df_snaps['value_in_inr'] < 0]['value_in_inr'].sum() * -1 # Render as a positive debt amount
        
        # Determine MoM and YoY Trends
        yoy_pct_str, yoy_val_str = "N/A", None
        mom_pct_str, mom_val_str = "N/A", None
        df_pivot = pd.DataFrame()
        
        if not df_all_snaps.empty:
            df_all_snaps['snapshot_date'] = pd.to_datetime(df_all_snaps['snapshot_date'])
            df_all_snaps['month_period'] = df_all_snaps['snapshot_date'].dt.to_period('M')
            
            df_pivot = df_all_snaps.pivot_table(
                index='month_period', columns='unique_entity_id', values='value_in_inr', aggfunc='last'
            ).fillna(0) 
            df_pivot['Total Net Worth'] = df_pivot.sum(axis=1)
            
            latest_period = df_pivot.index.max()
            
            # Month-over-Month calculation (Strictly looks 1 month back)
            prev_period = latest_period - 1
            if prev_period in df_pivot.index:
                prev_nw = df_pivot.loc[prev_period, 'Total Net Worth']
                if prev_nw != 0:
                    mom_pct = ((total_nw - prev_nw) / abs(prev_nw)) * 100
                    mom_pct_str = f"{mom_pct:,.2f}%"
                    mom_val_str = f"₹ {(total_nw - prev_nw):,.2f}"
                    
            # Year-over-Year calculation (Strictly looks 12 months back)
            prev_year_period = latest_period - 12
            if prev_year_period in df_pivot.index:
                prev_yr_nw = df_pivot.loc[prev_year_period, 'Total Net Worth']
                if prev_yr_nw != 0:
                    yoy_pct = ((total_nw - prev_yr_nw) / abs(prev_yr_nw)) * 100
                    yoy_pct_str = f"{yoy_pct:,.2f}%"
                    yoy_val_str = f"₹ {(total_nw - prev_yr_nw):,.2f}"

        # ---------------------------------------------------------
        # TOP ROW: 5-Column Key Metrics (Indian Format)
        # ---------------------------------------------------------
        st.subheader("Key Metrics")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        col1.metric("Current Assets", format_inr(current_assets))
        col2.metric("Current Liabilities", format_inr(current_liabilities))
        col3.metric(f"Net Worth ({latest_month_display})", format_inr(total_nw))
        
        # For YoY and MoM deltas, we format the delta values using the helper too
        yoy_delta_str = format_inr(total_nw - prev_yr_nw) if 'prev_yr_nw' in locals() and prev_yr_nw != 0 else None
        mom_delta_str = format_inr(total_nw - prev_nw) if 'prev_nw' in locals() and prev_nw != 0 else None

        col4.metric("YoY NW Growth", yoy_pct_str, delta=yoy_delta_str)
        col5.metric("MoM NW Growth", mom_pct_str, delta=mom_delta_str)
        
        st.divider()

        # ---------------------------------------------------------
        # Historical Net Worth Trend (Area Chart)
        # ---------------------------------------------------------
        st.subheader("Historical Net Worth Trend")
        if not df_pivot.empty:
            import plotly.express as px
            df_trend = df_pivot.reset_index()
            df_trend['chart_date'] = df_trend['month_period'].dt.to_timestamp()
            
            # Use your Indian currency helper for the chart data labels
            df_trend['formatted_nw'] = df_trend['Total Net Worth'].apply(format_inr)

            fig_area = px.area(
                df_trend, 
                x='chart_date', 
                y='Total Net Worth', 
                text='formatted_nw', # Passes the formatted Indian currency string
                color_discrete_sequence=['#00b4d8']
            )
            
            # Show data points (markers) and position the text labels above them
            fig_area.update_traces(
                mode='lines+markers+text',
                textposition='top center',
                textfont=dict(size=11)
            )
            
            fig_area.update_layout(
                xaxis_title="", 
                yaxis_title="Net Worth (INR)",
                margin=dict(l=20, r=20, t=30, b=0), # Added a bit of top margin so labels don't get cut off
                yaxis_tickformat="₹,.0f",
                xaxis=dict(tickformat="%b %Y", dtick="M1")
            )
            st.plotly_chart(fig_area, use_container_width=True)

        st.divider()

        # ---------------------------------------------------------
        # Interactive Asset Allocation (Donut + Table)
        # ---------------------------------------------------------
        st.subheader(f"Asset Allocation ({latest_month_display})")
        df_assets = df_snaps[df_snaps['value_in_inr'] > 0]
        
        col_pie, col_ast_table = st.columns([1.2, 1])
        
        with col_pie:
            if not df_assets.empty:
                import altair as alt 
                
                df_grouped_assets = df_assets.groupby('detailed_category')['value_in_inr'].sum().reset_index()
                
                click = alt.selection_point(name='click', fields=['detailed_category'])
                
                fig_donut = alt.Chart(df_grouped_assets).mark_arc(innerRadius=65).encode(
                    theta=alt.Theta(field="value_in_inr", type="quantitative"),
                    color=alt.Color(field="detailed_category", type="nominal", legend=alt.Legend(title="Type")),
                    opacity=alt.condition(click, alt.value(1.0), alt.value(0.3)), 
                    tooltip=[
                        alt.Tooltip("detailed_category", title="Category"),
                        alt.Tooltip("value_in_inr", title="Amount (INR)", format=",.2f")
                    ]
                ).add_params(click)
                
                pie_event = st.altair_chart(fig_donut, use_container_width=True, on_select="rerun")
                
                selected_category = None
                if pie_event and "selection" in pie_event and "click" in pie_event["selection"]:
                    if len(pie_event["selection"]["click"]) > 0:
                        selected_category = pie_event["selection"]["click"][0]["detailed_category"]
            else:
                st.info("No positive assets logged this month.")
                
        with col_ast_table:
            if not df_assets.empty:
                if selected_category:
                    st.write(f"**Selected:** {selected_category}")
                    display_df = df_assets[df_assets['detailed_category'] == selected_category]
                else:
                    st.write("**All Assets** (Click a pie slice to filter)")
                    display_df = df_assets
                    
                st.dataframe(
                    display_df[['entity_name', 'detailed_category', 'value_in_inr']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "entity_name": "Name", "detailed_category": "Type",
                        "value_in_inr": st.column_config.NumberColumn("Value (INR)", format="₹%.2f")
                    }
                )

        st.divider()

        # ---------------------------------------------------------
        # Interactive Liabilities Trend (Bar + Table)
        # ---------------------------------------------------------
        st.subheader("Liabilities Month-on-Month Trend")
        df_liabilities = df_all_snaps[df_all_snaps['value_in_inr'] < 0].copy()
        
        col_liab_chart, col_liab_table = st.columns([1.2, 1])
        
        with col_liab_chart:
            if not df_liabilities.empty:
                df_liabilities['abs_value'] = df_liabilities['value_in_inr'].abs()
                df_liabilities['chart_date'] = df_liabilities['month_period'].dt.to_timestamp()
                
                df_liab_trend = df_liabilities.groupby('chart_date')['abs_value'].sum().reset_index()
                
                import plotly.express as px
                fig_liab = px.bar(
                    df_liab_trend, x='chart_date', y='abs_value', 
                    color_discrete_sequence=['#ef476f']
                )
                fig_liab.update_layout(
                    xaxis_title="", yaxis_title="Total Liabilities (INR)",
                    margin=dict(l=0, r=0, t=10, b=0), yaxis_tickformat="₹,.0f",
                    xaxis=dict(tickformat="%b %Y", dtick="M1")
                )
                
                liab_event = st.plotly_chart(fig_liab, use_container_width=True, on_select="rerun")
                
                selected_month = None
                if liab_event and "selection" in liab_event and liab_event["selection"]["points"]:
                    selected_x = liab_event["selection"]["points"][0]["x"]
                    selected_month = pd.to_datetime(selected_x)
            else:
                st.success("No liabilities recorded! Great job.")
                
        with col_liab_table:
            if not df_liabilities.empty:
                if selected_month:
                    st.write(f"**Liabilities for:** {selected_month.strftime('%b %Y')}")
                    display_liab_df = df_liabilities[df_liabilities['month_period'] == selected_month.to_period('M')]
                else:
                    latest_liab_month = df_liabilities['month_period'].max()
                    st.write(f"**Liabilities for:** {latest_liab_month.strftime('%b %Y')} (Click a bar to change)")
                    display_liab_df = df_liabilities[df_liabilities['month_period'] == latest_liab_month]
                
                display_liab_df = display_liab_df.sort_values('snapshot_date').groupby('unique_entity_id').last().reset_index()
                    
                st.dataframe(
                    display_liab_df[['entity_name', 'detailed_category', 'abs_value']],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "entity_name": "Name", "detailed_category": "Type",
                        "abs_value": st.column_config.NumberColumn("Owed (INR)", format="₹%.2f")
                    }
                )

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
            # Convert to datetime to extract Month and Year dynamically
            df_snap['snapshot_date'] = pd.to_datetime(df_snap['snapshot_date'])
            df_snap['month_year'] = df_snap['snapshot_date'].dt.strftime('%B %Y') # e.g., "August 2026"
            
            # Get a unique, sorted list of available months from the data
            available_months = df_snap.sort_values('snapshot_date', ascending=False)['month_year'].unique().tolist()
            
            # Create the filter UI element
            col_filter, col_spacer = st.columns([2, 2])
            with col_filter:
                selected_month_filter = st.selectbox("Filter by Month & Year", ["All Time"] + available_months)
                
            # Apply the filter if something other than "All Time" is selected
            if selected_month_filter != "All Time":
                df_filtered = df_snap[df_snap['month_year'] == selected_month_filter]
            else:
                df_filtered = df_snap
                
            st.write(f"Showing **{len(df_filtered)}** record(s)")
            
            # Drop our helper columns before rendering the dataframe
            st.dataframe(
                df_filtered.drop(columns=['month_year']), use_container_width=True, hide_index=True,
                column_config={
                    "snapshot_date": "Date", "entity_type": "Category", "entity_name": "Item Name",
                    "balance_or_value": st.column_config.NumberColumn("Local Value", format="%.2f"),
                    "exchange_rate_to_inr": st.column_config.NumberColumn("FX to INR", format="%.4f"),
                    "value_in_inr": st.column_config.NumberColumn("INR Equivalent", format="₹%.2f"),
                    "notes": "Notes"
                }
            )
            
    with tab3:
        st.subheader("Modify or Remove a Snapshot")
        sql_edit_view = """
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
        df_edit_snap = conn.query(sql_edit_view, ttl=0)
        
        if not df_edit_snap.empty:
            snap_options = {f"{row['snapshot_date'].strftime('%Y-%m-%d')} - {row['entity_name']} (ID: {row['id']})": row['id'] for _, row in df_edit_snap.iterrows()}
            selected_snap_label = st.selectbox("Select Snapshot to Modify", list(snap_options.keys()))
            selected_id = snap_options[selected_snap_label]
            
            current_data = conn.query(f"SELECT * FROM baseline_snapshots WHERE id = {selected_id}", ttl=0).iloc[0]
            
            with st.form("edit_snapshot_form"):
                action = st.radio("Choose Action", ["Update Record", "Delete Record"], horizontal=True)
                st.write(f"**Editing Snapshot:** {selected_snap_label}")
                
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
                        
                    elif action == "UpdateRecord":
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

    # ==========================================
    # MODULE 6: FINANCIAL GOALS (FI TRACKING)
    # ==========================================
    elif menu == "Financial Goals":
        st.header("🎯 Financial Independence (FI) Goals")
        st.write("Set your target annual expenses and Safe Withdrawal Rate (SWR) to calculate your FI number.")

        # Fetch the current goals from the database
        df_goals = conn.query("SELECT * FROM financial_goals LIMIT 1", ttl=0)
        
        if not df_goals.empty:
            current_expenses = float(df_goals.iloc[0]['annual_expenses'])
            current_swr = float(df_goals.iloc[0]['safe_withdrawal_rate'])
            
            # Calculate the current target FI Number
            # FI Number = Annual Expenses / (SWR / 100)
            target_fi_number = current_expenses / (current_swr / 100)
            
            st.subheader("Your FI Target")
            st.metric("Financial Independence Number", format_inr(target_fi_number))
            st.divider()

            with st.form("update_goals_form"):
                st.subheader("Adjust Goal Parameters")
                col1, col2 = st.columns(2)
                
                with col1:
                    new_expenses = st.number_input(
                        "Target Annual Expenses (INR)", 
                        min_value=0.0, 
                        value=current_expenses, 
                        step=50000.0,
                        help="How much money do you need per year to live comfortably in retirement?"
                    )
                with col2:
                    new_swr = st.number_input(
                        "Safe Withdrawal Rate (%)", 
                        min_value=1.0, 
                        max_value=10.0, 
                        value=current_swr, 
                        step=0.25,
                        help="The standard Trinity Study rate is 4.0%. A more conservative rate is 3.5% or 3.0%."
                    )
                
                if st.form_submit_button("Update FI Goals"):
                    with conn.session as s:
                        sql = text("""
                            UPDATE financial_goals 
                            SET annual_expenses = :exp, safe_withdrawal_rate = :swr, last_updated = CURRENT_TIMESTAMP
                            WHERE id = 1
                        """)
                        s.execute(sql, {"exp": new_expenses, "swr": new_swr})
                        s.commit()
                    st.success("Financial goals updated successfully!")
                    time.sleep(1)
                    st.rerun()
        else:
            st.error("Financial goals table is empty or missing. Please run the SQL setup script.")
            )
