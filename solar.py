import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import fitz  # PyMuPDF for PDF generation
import os

# ---------------- SESSION STATE INIT ----------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'menu' not in st.session_state:
    st.session_state.menu = "Landing"
if 'username' not in st.session_state:
    st.session_state.username = ""

# ---------------- DATABASE FUNCTIONS ----------------
def get_connection():
    return sqlite3.connect('inventory.db')

def create_tables():
    conn = get_connection()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT,
        category TEXT,
        quantity INTEGER,
        unit_cost REAL,
        selling_price REAL,
        unit TEXT       
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT,
        quantity INTEGER,
        selling_price REAL,
        total_sale REAL,
        cost REAL,
        profit REAL,
        date TEXT,
        customer_id INTEGER
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        email TEXT,
        address TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT,
        category TEXT,
        action TEXT,
        quantity INTEGER,
        unit_cost REAL,
        selling_price REAL,
        user TEXT,
        timestamp TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS installations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        item_id INTEGER,
        quantity INTEGER,
        installed_by TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(item_id) REFERENCES items(id)
    )
    """)
    conn.commit()
    conn.close()

def view_items():
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM items', conn)
    conn.close()
    return df

def view_sales():
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM sales', conn)
    conn.close()
    return df

def view_customers():
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM customers', conn)
    conn.close()
    return df

def view_sales_by_customers(customer_id=None):
    conn = get_connection()
    
    if customer_id:
        query = 'SELECT * FROM sales WHERE customer_id = ?'
        df = pd.read_sql_query(query, conn, params=(customer_id,))
    else:
        query = 'SELECT * FROM sales'
        df = pd.read_sql_query(query, conn)
    
    conn.close()
    return df

def view_audit_log(start_date=None, end_date=None):
    conn = get_connection()
    if start_date and end_date:
        query = """
        SELECT * FROM audit_log
        WHERE DATE(timestamp) BETWEEN ? AND ?
        ORDER BY timestamp DESC
        """
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    else:
        df = pd.read_sql_query('SELECT * FROM audit_log ORDER BY timestamp DESC', conn)
    conn.close()
    return df

# ---------------- Record Installations ---------------
def record_installation(item_id, quantity, installed_by, customer_id, installed_date):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check current stocks on hand
        # Check current stocks on hand
        cursor.execute("SELECT quantity FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return f"Item {item_id} not found in inventory."
        
        current_stock = result[0]
        
        if current_stock < quantity:
            conn.close()
            return f"Not enough stock.  Current stock: {current_stock}, requested quantity: {quantity}."
        
        # Record installation
        cursor.execute("""
            INSERT INTO installations (customer_id, item_id, quantity, installed_by, date)
            VALUES (?, ?, ?, ?, ?)
        """, (customer_id, item_id, quantity, installed_by, installed_date))
        
        # Update Inventory (subtract installed quantity)
        cursor.execute("""
            UPDATE items
            SET quantity = quantity - ?
            WHERE id = ?
        """, (quantity, item_id))

        conn.commit()
        conn.close()
        return f"Installation recorded: Item {item_id}, Quantity {quantity}, for Customer {customer_id} on {installed_date} by {installed_by}."
    except Exception as e:
        return f"Error recording installation: {e}"
    
# --------------- View Installations -----------------
def view_installations():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.id, i.customer_id, c.name AS customer_name,
               i.item_id, it.item AS item_name,
               i.quantity, i.installed_by, i.date
        FROM installations i
        JOIN customers c ON i.customer_id = c.id
        JOIN items it ON i.item_id = it.id
        ORDER BY i.date DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    # Convert to DataFrame for Streamlit display
    df = pd.DataFrame(rows, columns=[
        "id", "customer_id", "customer_name",
        "item_id", "item_name", "quantity",
        "installed_by", "date"
    ])
    return df

# ---------------- Pagination Utility ----------------
def paginate_dataframe(df, page_size=20):
    total_rows = len(df)
    if total_rows == 0:
        return df, 1
    total_pages = (total_rows // page_size) + (1 if total_rows % page_size else 0)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    return df.iloc[start_idx:end_idx], total_pages

# ---------------- CRUD FUNCTIONS ----------------
def add_or_update_item(item, category, quantity, unit_cost, selling_price, unit, user):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, quantity FROM items WHERE item=? AND category=?', (item, category))
    existing = cursor.fetchone()
    if existing:
        new_quantity = existing[1] + quantity
        cursor.execute('UPDATE items SET quantity=?, unit_cost=?, selling_price=?, unit=? WHERE id=?',
                       (new_quantity, unit_cost, selling_price, unit, existing[0]))
        action = "Update"
    else:
        cursor.execute('INSERT INTO items (item, category, quantity, unit_cost, selling_price, unit) VALUES (?, ?, ?, ?, ?, ?)',
                       (item, category, quantity, unit_cost, selling_price, unit))
        action = "Add"
    cursor.execute('INSERT INTO audit_log (item, category, action, quantity, unit_cost, selling_price, user, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, DATETIME("now"))',
                   (item, category, action, quantity, unit_cost, selling_price, user))
    conn.commit()
    conn.close()

def delete_item(item_id, user):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT item, category, quantity, unit_cost, selling_price FROM items WHERE id=?', (item_id,))
    item_details = cursor.fetchone()
    if item_details:
        cursor.execute('INSERT INTO audit_log (item, category, action, quantity, unit_cost, selling_price, user, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, DATETIME("now"))',
                       (item_details[0], item_details[1], "Delete", item_details[2], item_details[3], item_details[4], user))
        cursor.execute('DELETE FROM items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()

def record_sale(item, quantity, user, customer_id):
    conn = get_connection()
    item_data = pd.read_sql_query(f"SELECT * FROM items WHERE item='{item}'", conn)
    if item_data.empty:
        conn.close()
        return "Item not found."
    row = item_data.iloc[0]
    if row['quantity'] < quantity:
        conn.close()
        return "Not enough stock."
    total_sale = quantity * row['selling_price']
    cost = quantity * row['unit_cost']
    profit = total_sale - cost
    conn.execute('UPDATE items SET quantity=? WHERE id=?', (row['quantity'] - quantity, row['id']))
    conn.execute('INSERT INTO sales (item, quantity, selling_price, total_sale, cost, profit, date, customer_id) VALUES (?, ?, ?, ?, ?, ?, DATE("now"), ?)',
                 (item, quantity, row['selling_price'], total_sale, cost, profit, customer_id))
    conn.execute('INSERT INTO audit_log (item, category, action, quantity, unit_cost, selling_price, user, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, DATETIME("now"))',
                 (item, row['category'], "Sale", quantity, row['unit_cost'], row['selling_price'], user))
    conn.commit()
    conn.close()
    return f"Sale recorded. Profit: ${profit:.2f}"

# ---------------- Excel/CSV import file for Stock Add/Update ----------------
def import_items_and_add_or_insert():
    # Prompt user for file path
    file_path = input("Please enter the full path to your Excel or CSV file: ").strip()

    # Determine file type and read accordingly
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext == '.csv':
        df = pd.read_csv(file_path)
    elif file_ext == '.xlsx':
        df = pd.read_excel(file_path, engine='openpyxl')
    elif file_ext == '.xls':
        df = pd.read_excel(file_path, engine='xlrd')
    else:
        raise ValueError("Unsupported file format. Please upload a CSV or Excel file.")

    # Connect to the database
    conn = get_connection()
    cursor = conn.cursor()

    # Process each item in the file
    for _, row in df.iterrows():
        item_id = row['item_id']
        category = row['category']
        unit_cost = row['unit_cost']
        selling_price = row['selling_price']
        quantity = row['stock_quantity']
        unit = row['unit']

        # Check if item exists
        cursor.execute("SELECT stock_quantity FROM items WHERE item_id = ?", (item_id))
        result = cursor.fetchone()

        if result:
            # Item exists, update stock quantity
            current_quantity = result[0]
            new_quantity = current_quantity + quantity
            cursor.execute("UPDATE items SET stock_quantity = ? WHERE item_id = ?", (new_quantity, item_id))
        else:
            # Item does not exist, insert new item
            cursor.execute("""
                INSERT INTO items (item_id, category, unit_cost, selling_price, stock_quantity, unit)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (item_id, category, unit_cost, selling_price, quantity, unit))

    # Commit changes and close connection
    conn.commit()
    conn.close()
    print("Items updated or inserted successfully.")


# ---------------- PDF Generation for SOA ----------------

# Blk 3 Lot 5 West Wing Villas, North Belton QC
# -*- coding: utf-8 -*-
import fitz
import os

def generate_soa_pdf(customer_name, customer_id, start_date, end_date, soa_df, logo_path="icon.jpeg"):
    pdf_filename = f"statement_customer_{customer_id}_{customer_name}.pdf"
    doc = fitz.open()

    # Path to Unicode font (download DejaVuSans.ttf and place in same folder)
    font_path = "DejaVuSans.ttf"  # Ensure this file exists in your working directory

    # Page settings
    page_width, page_height = 595, 842  # A4 size
    margin_left = 50
    row_height = 20
    col_positions = [50, 150, 250, 350, 450]  # Date, Item, Qty, Price, Total
    headers = ["Date", "Item", "Qty", "Price", "Total"]
    char_width = 6  # Approx width for alignment calculation

    def draw_header(page):
        # Logo
        if logo_path and os.path.exists(logo_path):
            rect = fitz.Rect(50, 20, 150, 80)
            page.insert_image(rect, filename=logo_path)

        # Company details
        page.insert_text((200, 40), "Alpha CJ Solar", fontsize=14, fontfile=font_path)
        page.insert_text((200, 60), "63-C Data St. Don Manuel QC | +63-917-891-3547", fontsize=10, fontfile=font_path)

        # SOA Title
        page.insert_text((margin_left, 100), "Statement of Account", fontsize=16, fontfile=font_path)
        page.insert_text((margin_left, 120), f"Customer: {customer_name} (ID: {customer_id})", fontsize=12, fontfile=font_path)
        page.insert_text((margin_left, 135), f"Period: {start_date} to {end_date}", fontsize=12, fontfile=font_path)

    def draw_table_header(page, y):
        # Left-aligned headers
        page.insert_text((col_positions[0], y), headers[0], fontsize=12, fontfile=font_path)
        page.insert_text((col_positions[1], y), headers[1], fontsize=12, fontfile=font_path)
        page.insert_text((col_positions[2], y), headers[2], fontsize=12, fontfile=font_path)

        # Right-align Price & Total headers
        price_header = headers[3]
        total_header = headers[4]
        price_x = col_positions[3] + 80 - (len(price_header) * char_width)
        total_x = col_positions[4] + 80 - (len(total_header) * char_width)
        page.insert_text((price_x, y), price_header, fontsize=12, fontfile=font_path)
        page.insert_text((total_x, y), total_header, fontsize=12, fontfile=font_path)

        # Horizontal line under header
        page.draw_line((col_positions[0], y + 15), (col_positions[-1] + 80, y + 15))
        return y + row_height + 5

    # Create first page
    page = doc.new_page(width=page_width, height=page_height)
    draw_header(page)
    y = draw_table_header(page, 160)

    # Table rows
    for idx, row in soa_df.iterrows():
        # New page if needed
        if y + row_height > page_height - 100:
            page = doc.new_page(width=page_width, height=page_height)
            draw_header(page)
            y = draw_table_header(page, 160)

        # Insert row text
        page.insert_text((col_positions[0], y), str(row['date']), fontsize=10, fontfile=font_path)
        page.insert_text((col_positions[1], y), str(row['item']), fontsize=10, fontfile=font_path)
        page.insert_text((col_positions[2], y), str(row['quantity']), fontsize=10, fontfile=font_path)

        # Right-align Price and Total with Peso symbol
        price_text = f"PHP{row['selling_price']:,.2f}"
        total_text = f"PHP{row['total_sale']:,.2f}"
        price_x = col_positions[3] + 80 - (len(price_text) * char_width)
        total_x = col_positions[4] + 80 - (len(total_text) * char_width)

        page.insert_text((price_x, y), price_text, fontsize=10, fontfile=font_path)
        page.insert_text((total_x, y), total_text, fontsize=10, fontfile=font_path)

        y += row_height

    # Summary row
    y += 20
    total_amount = soa_df['total_sale'].sum()
    total_qty = soa_df['quantity'].sum()
    transaction_count = len(soa_df)

    summary_text = f"Transactions: {transaction_count} | Total Qty: {total_qty}"
    page.insert_text((col_positions[0], y), summary_text, fontsize=11, fontfile=font_path)

    # Total Amount (right-aligned)
    y += 20
    total_text = f"Total: PHP{total_amount:,.2f}"
    total_x = col_positions[4] + 80 - (len(total_text) * char_width)
    page.insert_text((total_x, y), total_text, fontsize=12, fontfile=font_path)

    # Footer
    page.insert_text((margin_left, page_height - 50), "Thank you for choosing Steak Haven - Premium Quality Meat",
                     fontsize=10, color=(0.5, 0.5, 0.5), fontfile=font_path)

    doc.save(pdf_filename)
    doc.close()
    return pdf_filename

# ---------------- CREATE TABLES ----------------
create_tables()

# ---------------- LOGOUT FUNCTION ----------------
def logout():
    st.session_state.logged_in = False
    st.session_state.menu = "Landing"
    st.session_state.username = ""

# ---------------- LOGIN PAGE ----------------
if not st.session_state.logged_in:
    if os.path.exists("icon.jpeg"):
        st.image("icon.jpeg", width=250)
    st.title("Welcome to Alpha CJ Solar")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if (username == "admin" or username == "Admin") and password == "1234":
            st.session_state.logged_in = True
            st.session_state.menu = "Home"
            st.session_state.username = username
            try:
                st.rerun()
            except AttributeError:
                st.rerun()
        else:
            st.error("Invalid credentials")

# ---------------- MAIN APP ----------------
elif st.session_state.logged_in:
    if os.path.exists("icon.jpeg"):
        st.sidebar.image("icon.jpeg", width=150)
    st.sidebar.title("Menu")
    st.sidebar.button("Logout", on_click=logout)
    st.sidebar.header("Settings")
    stock_threshold = st.sidebar.number_input("Set Stock Alert Threshold", min_value=0, value=5)
    menu = st.sidebar.selectbox(
        "Select Option",
        ["Home", "Add/Update Stock", "File Upload (Stocks)", "View Inventory", "Delete Item", "Add Customer", "View Customers", "Record Installations", "Profit/Loss Report", "View Audit Log", "Customer Statement of Account"],
        index=["Home", "Add/Update Stock", "File Upload (Stocks)", "View Inventory", "Delete Item", "Add Customer", "View Customers", "Record Installations", "Profit/Loss Report", "View Audit Log", "Customer Statement of Account"].index(st.session_state.menu)
    )
    st.session_state.menu = menu

    #if os.path.exists("icon.jpeg"):
    #    st.image("icon.jpeg", width=150)

## Aileen Added

    # ---------------- HOME ----------------
    if menu == "Home":
        st.title("Dashboard")
        items_df = view_items()
        sales_df = view_sales()
        if not items_df.empty:
            st.subheader("Inventory Summary")
            st.metric("Total Items", len(items_df))
            st.metric("Total Stock Value", f"${(items_df['quantity'] * items_df['unit_cost']).sum():,.2f}")
            fig = px.bar(items_df, x='category', y='quantity', color='category', title="Stock by Category")
            st.plotly_chart(fig)
        if not sales_df.empty:
            st.subheader("Sales Summary")
            st.metric("Total Sales", f"${sales_df['total_sale'].sum():,.2f}")
            st.metric("Total Profit", f"${sales_df['profit'].sum():,.2f}")
            fig2 = px.line(sales_df, x='date', y='profit', title="Profit Trend Over Time")
            st.plotly_chart(fig2)

    # ---------------- ADD/UPDATE STOCK ----------------
    elif menu == "Add/Update Stock":
        st.title("Add or Update Stock")
        items_df = view_items()
        existing_items = sorted(items_df['item'].dropna().unique()) if not items_df.empty else []
        existing_categories = sorted(items_df['category'].dropna().unique()) if not items_df.empty else []
        item_options = ["Add New"] + existing_items
        category_options = ["Add New"] + existing_categories

        # Session state initialization
        if 'item_name' not in st.session_state: st.session_state.item_name = ""
        if 'category_name' not in st.session_state: st.session_state.category_name = ""
        if 'quantity' not in st.session_state: st.session_state.quantity = 1
        if 'unit_cost' not in st.session_state: st.session_state.unit_cost = 0.0
        if 'selling_price' not in st.session_state: st.session_state.selling_price = 0.0
        # Add new fields
        if 'unit' not in st.session_state: st.session_state.unit = ""
        # Add new fields
        if 'selected_item' not in st.session_state: st.session_state.selected_item = "Add New"
        if 'selected_category' not in st.session_state: st.session_state.selected_category = "Add New"
        if 'show_next_action' not in st.session_state: st.session_state.show_next_action = False

        selected_item = st.selectbox("Select Item", item_options, index=item_options.index(st.session_state.selected_item) if st.session_state.selected_item in item_options else 0)

        current_stock = None
        if selected_item != "Add New":
            item_details = items_df[items_df['item'] == selected_item].iloc[0]
            st.session_state.unit_cost = item_details['unit_cost']
            st.session_state.selling_price = item_details['selling_price']
            # Add new fields
            st.session_state.unit = item_details['unit']
            # Add new fields
            st.session_state.selected_category = item_details['category']
            st.markdown(f"<div style='background-color:#003366;color:white;padding:8px;border-radius:4px;'>Category: {st.session_state.selected_category}</div>", unsafe_allow_html=True)
            category_name = st.session_state.selected_category
            current_stock = item_details['quantity']

        if current_stock is not None:
            st.info(f"Stock Currently On Hand: {current_stock}")
        else:
            selected_category = st.selectbox("Select Category", category_options, index=category_options.index(st.session_state.selected_category) if st.session_state.selected_category in category_options else 0)
            category_name = selected_category
            if selected_item == "Add New" and selected_category == "Add New":
                category_name = st.text_input("Enter New Category Name")

        item_name = st.text_input("Enter New Item Name", value=st.session_state.item_name) if selected_item == "Add New" else selected_item
        quantity = st.number_input("Quantity to Add", min_value=1, value=st.session_state.quantity)
        unit_cost = st.number_input("Unit Cost", min_value=0.0, format="%.2f", value=st.session_state.unit_cost)
        selling_price = st.number_input("Selling Price", min_value=0.0, format="%.2f", value=st.session_state.selling_price)
        # Add new fields
        unit = st.text_input("Unit", value=st.session_state.unit) 
        # Add new fields
        if st.button("Save"):
            if item_name and category_name:
                add_or_update_item(item_name, category_name, quantity, unit_cost, selling_price, unit, st.session_state.username)
                st.success(f"Item '{item_name}' in category '{category_name}' updated successfully!")
                st.session_state.show_next_action = True
            else:
                st.error("Please provide valid item and category names.")

        if st.session_state.show_next_action:
            st.markdown("---")
            st.subheader("Next Action")
            next_action = st.radio("What would you like to do next?", ["Add/Update More Stock", "View Inventory"])
            if st.button("Continue"):
                if next_action == "Add/Update More Stock":
                    st.session_state.item_name = ""
                    st.session_state.category_name = ""
                    st.session_state.quantity = 1
                    st.session_state.unit_cost = 0.0
                    st.session_state.selling_price = 0.0
                    # Add new fields
                    st.session_state.unit = ""
                    # Add new fields
                    st.session_state.selected_item = "Add New"
                    st.session_state.selected_category = "Add New"
                    st.session_state.show_next_action = False
                    st.rerun()
                elif next_action == "View Inventory":
                    st.session_state.show_next_action = False
                    st.session_state.menu = "View Inventory"
                    st.rerun()

    # ---------------- File Upload (Stocks) ----------------
    elif menu == "File Upload (Stocks)":
        st.title("File Upload (Stocks)")
        uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])
        if uploaded_file is not None:
            # Read file based on extension
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext == ".csv":
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            # Validate columns
            required_cols = ["item", "category", "quantity", "unit_cost", "selling_price"]
            if all(col in df.columns for col in required_cols):
                conn = get_connection()
                cursor = conn.cursor()
                for _, row in df.iterrows():
                    add_or_update_item(row["item"], row["category"], row["quantity"], row["unit_cost"], row["selling_price"], row["unit"], st.session_state.username)
                conn.commit()
                conn.close()
                st.success("Items updated or inserted successfully!")
            else:
                st.error(f"Missing required columns: {required_cols}")

    # ---------------- VIEW INVENTORY ----------------
    elif menu == "View Inventory":
        st.title("Inventory Data")
        data = view_items()
        if data.empty:
            st.warning("No items found.")
        else:
            def highlight_low_stock(row):
                return ['background-color: #CC0000' if row['quantity'] < stock_threshold else '' for _ in row]
            paged_df, total_pages = paginate_dataframe(data, page_size=20)
            st.write(f"Showing {len(paged_df)} rows (Page size: 20)")
            # st.dataframe(paged_df.style.apply(highlight_low_stock, axis=1), width='stretch')
            st.dataframe(
                paged_df.style
                    .apply(highlight_low_stock, axis=1)
                    .format({"unit_cost": "{:.2f}", "selling_price": "{:.2f}"}),
                width='stretch'
                )
            csv_inventory = data.to_csv(index=False)
            st.download_button("Download Inventory CSV", data=csv_inventory, file_name="inventory.csv", mime="text/csv")

    # ---------------- VIEW AUDIT LOG ----------------
    elif menu == "View Audit Log":
        st.title("Inventory Audit Log")
        start_date = st.date_input("Start Date")
        end_date = st.date_input("End Date")

        if st.button("Filter"):
            audit_df = view_audit_log(start_date, end_date)
        else:
            audit_df = view_audit_log()

        if audit_df.empty:
            st.warning("No audit records found.")
        else:
            paged_audit, total_pages = paginate_dataframe(audit_df, page_size=20)
            st.write(f"Showing {len(paged_audit)} rows (Page size: 20)")
            st.dataframe(paged_audit)
            csv_audit = audit_df.to_csv(index=False)
            st.download_button("Download Audit Log CSV", data=csv_audit, file_name="audit_log.csv", mime="text/csv")

    # ---------------- DELETE ITEM ----------------
    elif menu == "Delete Item":
        st.title("Delete Item")
        data = view_items()
        if data.empty:
            st.warning("No items to delete.")
        else:
            data['label'] = data.apply(lambda row: f"{row['id']} - {row['category']} - {row['item']}", axis=1)
            selected_label = st.selectbox("Select Item to Delete", data['label'])
            item_id = int(selected_label.split(" - ")[0])
            if st.button("Delete"):
                delete_item(item_id, st.session_state.username)
                st.success(f"Item with ID {item_id} deleted successfully!")
                st.rerun()

    # ---------------- ADD CUSTOMER ----------------
    elif menu == "Add Customer":
        st.title("Add New Customer")
        name = st.text_input("Customer Name")
        phone = st.text_input("Phone")
        email = st.text_input("Email")
        address = st.text_area("Address")
        if st.button("Save Customer"):
            conn = get_connection()
            conn.execute('INSERT INTO customers (name, phone, email, address) VALUES (?, ?, ?, ?)',
                         (name, phone, email, address))
            conn.commit()
            conn.close()
            st.success(f"Customer '{name}' added successfully!")

    # ---------------- VIEW CUSTOMERS ----------------
    elif menu == "View Customers":
        st.title("Customer List")
        data = view_customers()
        if data.empty:
            st.warning("No customers found.")
        else:
            paged_customers, total_pages = paginate_dataframe(data, page_size=20)
            st.write(f"Showing {len(paged_customers)} rows (Page size: 20)")
            st.dataframe(paged_customers)

    ## Add new list
    elif menu == "Record Installations":
        st.title("Record Installations")
        items_df = view_items()
        customers_df = view_customers()

        if items_df.empty:
            st.warning("No items available in inventory.")
        elif customers_df.empty:
            st.warning("No customers available. Please add a customer first.")
        else:
            # Customer selection
            customer_label = st.selectbox(
                "Select Customer",
                customers_df.apply(lambda row: f"{row['id']} - {row['name']}", axis=1)
            )
            customer_id = int(customer_label.split(" - ")[0])

            # Item selection
            item_label = st.selectbox(
                "Select Item to Install",
                items_df.apply(lambda row: f"{row['id']} - {row['item']}", axis=1)
            )
            item_id = int(item_label.split(" - ")[0])

            # Quantity input
            quantity = st.number_input("Quantity to Install", min_value=1)

            # Installed by
            installed_by = st.text_input("Installed By: ")

            # Install Date
            installed_date = st.date_input ("Installation Date: ")

            # Record Installation button
            if st.button("Record Installation"):
                result = record_installation(item_id, quantity, installed_by, customer_id, installed_date)
                st.success(result)

            # Show Installations for selected customer
            st.subheader(f"Installations for Customer ID {customer_id}")
            installations_df = view_installations()

            if not installations_df.empty:
                customer_installs = installations_df[installations_df['customer_id'] == customer_id]

                if not customer_installs.empty:
                    st.dataframe(customer_installs)
                    csv_installs = customer_installs.to_csv(index=False)
                    st.download_button(
                        "Download Customer Installations CSV",
                        data=csv_installs,
                        file_name=f"customer_{customer_id}_installations.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No installations recorded yet for this customer.")
            else:
                st.info("No installations recorded yet.")


    ## Add new list
    # ---------------- PROFIT/LOSS REPORT ----------------
    elif menu == "Profit/Loss Report":
        st.title("Profit/Loss Report")
        sales_df = view_sales()
        if sales_df.empty:
            st.warning("No sales data available.")
        else:
            total_sales = sales_df['total_sale'].sum()
            total_cost = sales_df['cost'].sum()
            total_profit = sales_df['profit'].sum()
            st.metric("Total Sales", f"${total_sales:,.2f}")
            st.metric("Total Cost", f"${total_cost:,.2f}")
            st.metric("Total Profit", f"${total_profit:,.2f}")
            paged_sales, total_pages = paginate_dataframe(sales_df, page_size=20)
            st.write(f"Showing {len(paged_sales)} rows (Page size: 20)")
            st.dataframe(paged_sales)
            csv_sales = sales_df.to_csv(index=False)
            st.download_button("Download Sales CSV", data=csv_sales, file_name="sales.csv", mime="text/csv")
## Aileen Added

    # ---------------- CUSTOMER SOA ----------------
    # --- CUSTOMER SOA ---
    elif menu == "Customer Statement of Account":
        st.title("Customer Statement of Account")
        customers_df = view_customers()
        if customers_df.empty:
            st.warning("No customers found.")
        else:
            # Customer selection
            customer_label = st.selectbox(
                "Select Customer",
                customers_df.apply(lambda row: f"{row['id']} - {row['name']}", axis=1)
            )
            customer_id = int(customer_label.split(" - ")[0])
            customer_name = customer_label.split(" - ")[1]

            # Date filters
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")

            # Fetch filtered sales data
            def view_sales_by_customer_and_date(customer_id, start_date=None, end_date=None):
                conn = get_connection()
                if start_date and end_date:
                    query = """
                    SELECT * FROM sales
                    WHERE customer_id = ? AND date BETWEEN ? AND ?
                    """
                    df = pd.read_sql_query(query, conn, params=(customer_id, start_date, end_date))
                else:
                    query = "SELECT * FROM sales WHERE customer_id = ?"
                    df = pd.read_sql_query(query, conn, params=(customer_id,))
                conn.close()
                return df

            # Display filtered table
            sales_customer = view_sales_by_customer_and_date(customer_id, start_date, end_date)
            if sales_customer.empty:
                st.warning("No sales records found for this customer in the selected period.")
            else:
                st.subheader("Sales Records of Selected Customer")
                paged_sales_customer, total_pages = paginate_dataframe(sales_customer, page_size=20)
                st.write(f"Showing {len(paged_sales_customer)} rows (Page size: 20)")
                st.dataframe(paged_sales_customer)

                # Download CSV
                csv_sales = sales_customer.to_csv(index=False)
                st.download_button("Download Sales CSV", data=csv_sales, file_name="sales_customer.csv", mime="text/csv")

                # Generate SOA PDF
                if st.button("Generate SOA"):
                    pdf_file = generate_soa_pdf(customer_name, customer_id, start_date, end_date, sales_customer)
                    with open(pdf_file, "rb") as f:
                        st.download_button("Download SOA PDF", data=f, file_name=pdf_file, mime="applic-ation/pdf")
    
    
    
    
    

