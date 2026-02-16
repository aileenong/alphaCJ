# solar.py (Supabase version)
import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import fitz  # PyMuPDF for PDF generation
import os
import io
import base64
import cv2
from pyzbar.pyzbar import decode
import datetime
from datetime import datetime
from datetime import date

# Import Supabase-backed functions
from db_supabase import (
    view_items, view_sales, view_customers, view_sales_by_customers, view_audit_log,
    delete_customer, record_installation, delete_all_inventory, delete_all_customers,
    view_installations, paginate_dataframe, add_or_update_item, delete_item,
    record_sale, import_items_and_add_or_insert, delete_customer_installation,
    add_customer, view_sales_by_customer_and_date
)

# ---------------- SESSION STATE INIT ----------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'menu' not in st.session_state:
    st.session_state.menu = "Landing"
if 'username' not in st.session_state:
    st.session_state.username = ""

# ---------------- LOGOUT FUNCTION ----------------
def logout():
    st.session_state.logged_in = False
    st.session_state.menu = "Landing"
    st.session_state.username = ""

# ---------------- PDF Generation for SOA ----------------
# -*- coding: utf-8 -*-
import fitz as _fitz_inner
import os as _os_inner

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
        price_text = f"PHP{float(row['selling_price']):,.2f}"
        total_text = f"PHP{float(row['total_sale']):,.2f}"
        price_x = col_positions[3] + 80 - (len(price_text) * char_width)
        total_x = col_positions[4] + 80 - (len(total_text) * char_width)

        page.insert_text((price_x, y), price_text, fontsize=10, fontfile=font_path)
        page.insert_text((total_x, y), total_text, fontsize=10, fontfile=font_path)

        y += row_height

    # Summary row
    y += 20
    total_amount = float(soa_df['total_sale'].sum())
    total_qty = int(soa_df['quantity'].sum())
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
    stock_threshold = st.sidebar.number_input("Set Stock Alert Threshold", min_value=0, value=1)

    with st.sidebar:
        # Main menu
        main_menu = option_menu(
            "Main Menu",
            ["Home", "Inventory", "Customer", "Reports"],
            icons=["house", "box", "people", "bar-chart"],
            menu_icon="cast",
            default_index=0
        )

        # Submenu depending on main menu
        if main_menu == "Home":
            menu = option_menu("Home", ["Home"], icons=["house"])
        elif main_menu == "Inventory":
            menu = option_menu("Inventory", [
                "View Inventory",
                "Add/Update Stock",
                "File Upload (Stocks)",
                "Delete Item",
                "Delete All Inventory"
            ], icons=["plus-circle", "upload", "list", "trash", "trash"])
        elif main_menu == "Customer":
            menu = option_menu("Customer", [
                "View Customers",
                "View Installations for a Customer",
                "Add Customer",
                "File Upload (Customers)",
                "Record Installations",
                "Customer Statement of Account",
                "Delete All Customers"
            ], icons=["person-plus", "people", "gear", "upload", "clipboard", "file-text", "trash"])
        elif main_menu == "Reports":
            menu = option_menu("Reports", [
                "Profit/Loss Report",
                "View Audit Log"
            ], icons=["graph-up", "book"])

    st.session_state.menu = menu
    st.write(f"Selected: {main_menu} → {menu}")

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
            st.plotly_chart(fig, width='stretch')
        if not sales_df.empty:
            st.subheader("Sales Summary")
            st.metric("Total Sales", f"${sales_df['total_sale'].sum():,.2f}")
            st.metric("Total Profit", f"${sales_df['profit'].sum():,.2f}")
            fig2 = px.line(sales_df, x='date', y='profit', title="Profit Trend Over Time")
            st.plotly_chart(fig2, width='stretch')

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
        if 'unit' not in st.session_state: st.session_state.unit = ""
        if 'selected_item' not in st.session_state: st.session_state.selected_item = "Add New"
        if 'selected_category' not in st.session_state: st.session_state.selected_category = "Add New"
        if 'show_next_action' not in st.session_state: st.session_state.show_next_action = False

        selected_item = st.selectbox("Select Item", item_options, index=item_options.index(st.session_state.selected_item) if st.session_state.selected_item in item_options else 0)

        current_stock = None
        if selected_item != "Add New":
            item_details = items_df[items_df['item'] == selected_item].iloc[0]
            st.session_state.unit_cost = float(item_details['unit_cost'] or 0)
            st.session_state.selling_price = float(item_details['selling_price'] or 0)
            st.session_state.unit = item_details.get('unit', "") if isinstance(item_details.get('unit', ""), str) else ""
            st.session_state.selected_category = item_details['category']
            st.markdown(f"<div style='background-color:#003366;color:white;padding:8px;border-radius:4px;'>Category: {st.session_state.selected_category}</div>", unsafe_allow_html=True)
            category_name = st.session_state.selected_category
            current_stock = int(item_details['quantity'])

        if current_stock is not None:
            st.info(f"Stock Currently On Hand: {current_stock}")
        else:
            selected_category = st.selectbox("Select Category", category_options, index=category_options.index(st.session_state.selected_category) if st.session_state.selected_category in category_options else 0)
            category_name = selected_category
            if selected_item == "Add New" and selected_category == "Add New":
                category_name = st.text_input("Enter New Category Name")

        item_name = st.text_input("Enter New Item Name", value=st.session_state.item_name) if selected_item == "Add New" else selected_item
        quantity = st.number_input("Quantity to Add", min_value=1, value=st.session_state.quantity)
        unit_cost = st.number_input("Unit Cost", min_value=0.0, format="%.2f", value=float(st.session_state.unit_cost))
        selling_price = st.number_input("Selling Price", min_value=0.0, format="%.2f", value=float(st.session_state.selling_price))
        unit = st.text_input("Unit", value=st.session_state.unit)

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
                    st.session_state.unit = ""
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

        import re, os, pandas as pd

        def clean_currency_str(x: str) -> str:
            if x is None:
                return ""
            s = str(x).strip()
            if s == "" or s.lower() in ("nan", "none", "null"):
                return ""
            s = re.sub(r"[^\d,.\-]", "", s)
            if "," in s and "." in s:
                s = s.replace(",", "")
            elif "," in s and "." not in s:
                s = s.replace(",", ".")
            return s

        def as_float_safe(v, default=0.0):
            try:
                if v is None or (isinstance(v, float) and (v != v)):
                    return float(default)
                s = clean_currency_str(v)
                if s == "":
                    return float(default)
                f = float(s)
                if f in (float("inf"), float("-inf")):
                    return float(default)
                return float(f)
            except Exception:
                return float(default)

        def as_int_safe(v, default=0):
            try:
                f = as_float_safe(v, default=default)
                return int(round(f))
            except Exception:
                return int(default)

        def as_str_safe(v, default=""):
            if v is None:
                return default
            s = str(v).strip()
            if s.lower() in ("nan", "none", "null"):
                return default
            return s

        if uploaded_file is not None:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            try:
                if ext == ".csv":
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
            except Exception as e:
                st.error(f"Failed to read file: {e}")
                st.stop()

            df.columns = [c.strip() for c in df.columns]

            required_cols = ["item", "category", "quantity", "unit_cost", "selling_price"]
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}. Found: {list(df.columns)}")
                st.stop()

            records, errors_prepare = [], []
            for idx, row in df.iterrows():
                item = as_str_safe(row.get("item", ""))
                category = as_str_safe(row.get("category", ""))
                quantity = as_int_safe(row.get("quantity", 0))
                unit_cost = as_float_safe(row.get("unit_cost", 0.0))
                selling_price = as_float_safe(row.get("selling_price", 0.0))
                unit = as_str_safe(row.get("unit", "")) if "unit" in df.columns else ""

                if not item:
                    errors_prepare.append((idx + 1, "Missing item name"))
                    continue

                records.append({
                    "item": item.strip(),
                    "category": category.strip(),
                    "quantity": quantity,
                    "unit_cost": unit_cost,
                    "selling_price": selling_price,
                    "unit": unit or None
                })

            if errors_prepare:
                st.warning("Some rows were skipped during preparation:")
                st.dataframe(pd.DataFrame(errors_prepare, columns=["Row # (1-based)", "Reason"]), use_container_width=True)

            if not records:
                st.info("No valid rows to import after cleaning.")
                st.stop()

            from db_supabase import get_supabase
            sb = get_supabase()
            ok_count, fail_rows = 0, []

            st.info(f"Attempting batch upsert of {len(records)} rows...")
            try:
                BATCH = 500
                for i in range(0, len(records), BATCH):
                    chunk = records[i:i+BATCH]
                    safe_chunk = [{
                        "item": r["item"],
                        "category": r["category"] or "",
                        "quantity": int(r["quantity"] or 0),
                        "unit_cost": float(r["unit_cost"] or 0.0),
                        "selling_price": float(r["selling_price"] or 0.0),
                        "unit": r["unit"] if r["unit"] else None
                    } for r in chunk]

                    # ✅ Correct Supabase syntax: conflict columns as list
                    sb.table("items").upsert(safe_chunk, on_conflict=["item", "category"]).execute()
                    #sb.table("items").upsert(safe_chunk, on_conflict="items_item_category_key").execute()
                    ok_count += len(safe_chunk)

                st.success(f"✅ Imported {ok_count} rows successfully (batch upsert).")
            except Exception as batch_err:
                st.info("Batch upsert fell back to per‑row mode. Data is still being updated correctly.")
                ok_count = 0
                for idx, r in enumerate(records):
                    try:
                        add_or_update_item(
                            item=r["item"],
                            category=r["category"] or "",
                            quantity=int(r["quantity"] or 0),
                            unit_cost=float(r["unit_cost"] or 0.0),
                            selling_price=float(r["selling_price"] or 0.0),
                            unit=r["unit"] or "",
                            user=st.session_state.username,
                        )
                        ok_count += 1
                    except Exception as row_err:
                        fail_rows.append((idx + 1, r.get("item", ""), str(row_err)))

                st.success(f"✅ Imported {ok_count}/{len(records)} rows successfully (per-row).")
                if fail_rows:
                    st.error("Some rows failed:")
                    st.dataframe(pd.DataFrame(fail_rows, columns=["Row # (1-based)", "Item", "Error"]), use_container_width=True)

            st.toast("Upload complete.", icon="✅")
            
    # ---------------- VIEW INVENTORY ----------------
    elif menu == "View Inventory":
        st.title("Inventory Data")
        data = view_items()
        if data.empty:
            st.warning("No items found.")
        else:
            categories = data['category'].dropna().unique().tolist()
            selected_category = st.selectbox("Filter by Category", ["All"] + categories)

            if selected_category != "All":
                data = data[data['category'] == selected_category]

            def highlight_low_stock(row):
                return ['background-color: #CC0000' if row['quantity'] < stock_threshold else '' for _ in row]

            paged_df, total_pages = paginate_dataframe(data, page_size=100)
            st.write(f"Showing {len(paged_df)} rows (Page size: 100)")
            st.dataframe(
                paged_df.style
                    .apply(highlight_low_stock, axis=1)
                    .format({"unit_cost": "{:.2f}", "selling_price": "{:.2f}"}),
                width='stretch'
            )
            csv_inventory = data.to_csv(index=False)
            st.download_button("Download Inventory CSV", data=csv_inventory, file_name="inventory.csv", mime="text/csv")

    # ---------------- DELETE ALL INVENTORY ----------------
    elif menu == "Delete All Inventory":
        st.title("Delete All Inventory")
        st.warning("This action will delete ALL inventory items permanently.")
        confirm = st.text_input("Type 'DELETE' to confirm")
        if st.button("Delete All Inventory"):
            if confirm == "DELETE":
                delete_all_inventory()
                st.success("All inventory items have been deleted.")
            else:
                st.error("Confirmation text does not match. Inventory not deleted.")

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
            st.dataframe(paged_audit, width='stretch')
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
        name = st.text_input("Customer Name").upper()
        phone = st.text_input("Phone")
        email = st.text_input("Email").upper()
        address = st.text_area("Address").upper()

        if st.button("Save Customer"):
            msg = add_customer(name, phone, email, address)
            if "already exists" in msg:
                st.error(msg)
            else:
                st.success(msg)

    # ---------------- VIEW CUSTOMERS ----------------
    elif menu == "View Customers":
        st.title("Customer List")
        data = view_customers()
        if data.empty:
            st.warning("No customers found.")
        else:
            paged_customers, total_pages = paginate_dataframe(data, page_size=20)
            st.write(f"Showing {len(paged_customers)} rows (Page size: 100)")
            st.dataframe(paged_customers, width='stretch')

            # --- Delete customer option ---
            st.subheader("Delete a Customer")
            customer_names = data['name'].tolist()
            selected_customer = st.selectbox("Select Customer to Delete", customer_names)

            if st.button("Delete Customer"):
                delete_customer(selected_customer)
                st.success(f"Customer '{selected_customer}' has been deleted.")
                st.session_state["refresh_customers"] = True

            if st.session_state.get("refresh_customers", False):
                data = view_customers()
                st.session_state["refresh_customers"] = False

    # ---------------- FILE UPLOAD (CUSTOMERS) ----------------
    elif menu == "File Upload (Customers)":
        st.title("File Upload (Customers)")
        uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])

        if uploaded_file is not None:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            try:
                if ext == ".csv":
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
            except Exception as e:
                st.error(f"Failed to read file: {e}")
                st.stop()

            df.columns = [c.strip() for c in df.columns]
            required_cols = ["name", "phone", "email", "address"]
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}. Found: {list(df.columns)}")
                st.stop()

            success_count, fail_rows = 0, []
            for idx, row in df.iterrows():
                name = str(row.get("name", "")).strip().upper()
                phone = str(row.get("phone", "")).strip()
                email = str(row.get("email", "")).strip().upper()
                address = str(row.get("address", "")).strip().upper()

                if not name:
                    fail_rows.append((idx + 1, "Missing customer name"))
                    continue

                result = add_customer(name, phone, email, address)
                if "already exists" in result.lower() or "error" in result.lower():
                    fail_rows.append((idx + 1, name, result))
                else:
                    success_count += 1

            st.success(f"✅ Imported {success_count} customers successfully.")
            if fail_rows:
                st.warning("Some rows were not imported:")
                st.dataframe(pd.DataFrame(fail_rows, columns=["Row # (1-based)", "Customer Name", "Error"]), use_container_width=True)

    # ---------------- VIEW INSTALLATIONS FOR A CUSTOMER ----------------
    elif menu == "View Installations for a Customer":
        st.subheader("View Installations for a Customer")
        data = view_customers()
        if data.empty:
            st.info("No customers yet.")
        else:
            customer_names = data['name'].tolist()
            selected_customer_view = st.selectbox("Select Customer to View Installations", customer_names, key="view_install_customer")
            customer_row = data[data['name'] == selected_customer_view].iloc[0]
            customer_id = int(customer_row['id'])
            installations_df = view_installations()
            if not installations_df.empty:
                customer_installs = installations_df[installations_df['customer_id'] == customer_id]
                if not customer_installs.empty:
                    st.dataframe(customer_installs, width='stretch')
                    csv_installs = customer_installs.to_csv(index=False)
                    st.download_button(
                        "Download Customer Installations CSV",
                        data=csv_installs,
                        file_name=f"customer_{customer_id}_installations.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No installations recorded yet for this customer.")

            # --- Delete installation option ---
            st.subheader("Delete an Installation for a Customer")
            customer_installs_df = installations_df[installations_df['customer_id'] == customer_id] if not installations_df.empty else pd.DataFrame()

            if not customer_installs_df.empty:
                install_labels = customer_installs_df.apply(
                    lambda row: f"{row['id']} - {row['item_name']} ({row['quantity']} units on {row['date']})",
                    axis=1
                ).tolist()

                selected_label = st.selectbox("Select Installation to Delete", install_labels)
                install_id = int(selected_label.split(" - ")[0])

                if st.button("Delete Installation"):
                    result = delete_customer_installation(install_id)
                    st.success(result)
                    st.session_state["refresh_customers"] = True
            else:
                st.info("No installations recorded yet for this customer.")

    # ---------------- RECORD INSTALLATIONS ----------------
    elif menu == "Record Installations":
        st.title("Record Installations")
        items_df = view_items()
        customers_df = view_customers()

        if items_df.empty:
            st.warning("No items available in inventory.")
        elif customers_df.empty:
            st.warning("No customers available. Please add a customer first.")
        else:
            customer_label = st.selectbox(
                "Select Customer",
                customers_df.apply(lambda row: f"{row['id']} - {row['name']}", axis=1)
            )
            customer_id = int(customer_label.split(" - ")[0])

            item_label = st.selectbox(
                "Select Item to Install",
                items_df.apply(lambda row: f"{row['id']} - {row['item']}", axis=1)
            )
            item_id = int(item_label.split(" - ")[0])

            quantity = st.number_input("Quantity to Install", min_value=1)
            installed_by = st.text_input("Installed By: ")
            installed_date = st.date_input("Installation Date: ")

            if st.button("Record Installation"):
                result = record_installation(item_id, quantity, installed_by, customer_id, installed_date)
                if result.lower().startswith("error") or "Not enough stock" in result:
                    st.error(result)
                else:
                    st.success(result)

            st.subheader(f"Installations for Customer ID {customer_id}")
            installations_df = view_installations()

            if not installations_df.empty:
                customer_installs = installations_df[installations_df['customer_id'] == customer_id]
                if not customer_installs.empty:
                    st.dataframe(customer_installs, width='stretch')
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

    # ---------------- PROFIT/LOSS REPORT ----------------
    elif menu == "Profit/Loss Report":
        st.title("Profit/Loss Report")
        sales_df = view_sales()
        if sales_df.empty:
            st.warning("No sales data available.")
        else:
            total_sales = float(sales_df['total_sale'].sum())
            total_cost = float(sales_df['cost'].sum())
            total_profit = float(sales_df['profit'].sum())
            st.metric("Total Sales", f"${total_sales:,.2f}")
            st.metric("Total Cost", f"${total_cost:,.2f}")
            st.metric("Total Profit", f"${total_profit:,.2f}")
            paged_sales, total_pages = paginate_dataframe(sales_df, page_size=20)
            st.write(f"Showing {len(paged_sales)} rows (Page size: 20)")
            st.dataframe(paged_sales, width='stretch')
            csv_sales = sales_df.to_csv(index=False)
            st.download_button("Download Sales CSV", data=csv_sales, file_name="sales.csv", mime="text/csv")

    # ---------------- CUSTOMER SOA ----------------
    elif menu == "Customer Statement of Account":
        st.title("Customer Statement of Account")
        customers_df = view_customers()
        if customers_df.empty:
            st.warning("No customers found.")
        else:
            customer_label = st.selectbox(
                "Select Customer",
                customers_df.apply(lambda row: f"{row['id']} - {row['name']}", axis=1)
            )
            customer_id = int(customer_label.split(" - ")[0])
            customer_name = customer_label.split(" - ")[1]

            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")

            sales_customer = view_sales_by_customer_and_date(customer_id, start_date, end_date)
            if sales_customer.empty:
                st.warning("No sales records found for this customer in the selected period.")
            else:
                st.subheader("Sales Records of Selected Customer")
                paged_sales_customer, total_pages = paginate_dataframe(sales_customer, page_size=20)
                st.write(f"Showing {len(paged_sales_customer)} rows (Page size: 20)")
                st.dataframe(paged_sales_customer, width='stretch')

                csv_sales = sales_customer.to_csv(index=False)
                st.download_button("Download Sales CSV", data=csv_sales, file_name="sales_customer.csv", mime="text/csv")

                if st.button("Generate SOA"):
                    pdf_file = generate_soa_pdf(customer_name, customer_id, start_date, end_date, sales_customer)
                    with open(pdf_file, "rb") as f:
                        st.download_button("Download SOA PDF", data=f, file_name=pdf_file, mime="application/pdf")

    # ---------------- DELETE ALL CUSTOMERS ----------------
    elif menu == "Delete All Customers":
        st.title("Delete All Customers")
        st.warning("This action will delete ALL customers permanently.")
        confirm = st.text_input("Type 'DELETE' to confirm")
        if st.button("Delete All Customers"):
            if confirm == "DELETE":
                delete_all_customers()
                st.success("All customers have been deleted.")
            else:
                st.error("Confirmation text does not match. Customers not deleted.")

