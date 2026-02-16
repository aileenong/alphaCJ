# db_supabase.py
import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date
from typing import Optional

# ---------------- Supabase Client ----------------
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_role_key"]  # server-side only
    return create_client(url, key)

# ---------------- Helpers ----------------
def _to_date_str(d) -> str:
    if isinstance(d, (datetime, date)):
        return d.strftime("%Y-%m-%d")
    return str(d)

# ---------------- VIEW FUNCTIONS (SELECTs) ----------------
def view_items() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("items").select("*").order("item").execute()
    return pd.DataFrame(res.data or [])

def view_sales() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("sales").select("*").order("date", desc=True).execute()
    return pd.DataFrame(res.data or [])

def view_customers() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("customers").select("*").order("name").execute()
    return pd.DataFrame(res.data or [])

def view_sales_by_customers(customer_id: Optional[int] = None) -> pd.DataFrame:
    sb = get_supabase()
    q = sb.table("sales").select("*")
    if customer_id:
        q = q.eq("customer_id", customer_id)
    res = q.order("date", desc=True).execute()
    return pd.DataFrame(res.data or [])

def view_sales_by_customer_and_date(customer_id: int, start_date=None, end_date=None) -> pd.DataFrame:
    """
    Filter sales by customer and optional date range (inclusive).
    Dates can be date/datetime or 'YYYY-MM-DD'.
    """
    sb = get_supabase()
    q = sb.table("sales").select("*").eq("customer_id", customer_id)
    if start_date and end_date:
        s = _to_date_str(start_date)
        e = _to_date_str(end_date)
        q = q.gte("date", s).lte("date", e)
    res = q.order("date", desc=True).execute()
    return pd.DataFrame(res.data or [])

def view_installations() -> pd.DataFrame:
    """
    Mirrors your JOIN using the SQL view created earlier.
    """
    sb = get_supabase()
    res = sb.table("installations_view").select("*").execute()
    df = pd.DataFrame(res.data or [])
    expected_cols = [
        "id", "customer_id", "customer_name",
        "item_id", "item_name", "quantity",
        "installed_by", "date"
    ]
    if not df.empty:
        cols = [c for c in expected_cols if c in df.columns]
        df = df[cols]
    return df

def view_audit_log(start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    sb = get_supabase()
    q = sb.table("audit_log").select("*")
    if start_date and end_date:
        s = _to_date_str(start_date) + "T00:00:00Z"
        e = _to_date_str(end_date) + "T23:59:59Z"
        q = q.gte("timestamp", s).lte("timestamp", e)
    res = q.order("timestamp", desc=True).execute()
    return pd.DataFrame(res.data or [])

# ---------------- Pagination Utility (unchanged) ----------------
def paginate_dataframe(df: pd.DataFrame, page_size: int = 20):
    total_rows = len(df)
    if total_rows == 0:
        return df, 1
    total_pages = (total_rows // page_size) + (1 if total_rows % page_size else 0)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    return df.iloc[start_idx:end_idx], total_pages

# ---------------- CRUD / ACTIONS ----------------
def add_or_update_item(item: str, category: str, quantity: int, unit_cost: float,
                       selling_price: float, unit: str, user: str):
    """
    Atomic upsert + audit via RPC add_or_update_item
    """
    sb = get_supabase()
    payload = {
        "p_item": item,
        "p_category": category or "",
        "p_quantity": int(quantity),
        "p_unit_cost": float(unit_cost or 0),
        "p_selling_price": float(selling_price or 0),
        "p_unit": unit,
        "p_user": user,
    }
    res = sb.rpc("add_or_update_item", payload).execute()
    return res.data[0] if res.data else None

def delete_item(item_id: int, user: str):
    """
    Delete item with audit via RPC
    """
    sb = get_supabase()
    res = sb.rpc("delete_item_with_audit", {"p_item_id": int(item_id), "p_user": user}).execute()
    return bool(res.data) if res.data is not None else False

def record_sale(item: str, quantity: int, user: str, customer_id: Optional[int]):
    """
    Mirrors your logic and returns the same message format.
    """
    sb = get_supabase()
    try:
        res = sb.rpc(
            "record_sale",
            {
                "p_item": item,
                "p_quantity": int(quantity),
                "p_user": user,
                "p_customer_id": customer_id,
            }
        ).execute()
        if not res.data:
            return "Sale recorded, but no data returned."
        row = res.data[0]
        profit = float(row.get("profit", 0))
        return f"Sale recorded. Profit: ${profit:.2f}"
    except Exception as e:
        msg = str(e)
        if "Not enough stock" in msg:
            return "Not enough stock."
        if "Item" in msg and "not found" in msg:
            return "Item not found."
        return f"Error recording sale: {msg}"

def record_installation(item_id: int, quantity: int, installed_by: str,
                        customer_id: int, installed_date):
    """
    Atomic decrement + installation insert via RPC.
    """
    sb = get_supabase()
    try:
        res = sb.rpc(
            "record_installation",
            {
                "p_item_id": int(item_id),
                "p_quantity": int(quantity),
                "p_installed_by": installed_by,
                "p_customer_id": int(customer_id),
                "p_installed_date": (_to_date_str(installed_date) + "T00:00:00Z") if installed_date else None
            }
        ).execute()
        if not res.data:
            return f"Installation recorded: Item {item_id}, Quantity {quantity}, for Customer {customer_id} on {installed_date} by {installed_by}."
        return f"Installation recorded: Item {item_id}, Quantity {quantity}, for Customer {customer_id} on {installed_date} by {installed_by}."
    except Exception as e:
        msg = str(e)
        if "Not enough stock" in msg:
            try:
                item = sb.table("items").select("quantity").eq("id", item_id).single().execute().data
                current_stock = item["quantity"] if item else "unknown"
            except:
                current_stock = "unknown"
            return f"Not enough stock.  Current stock: {current_stock}, requested quantity: {quantity}."
        if "not found" in msg:
            return f"Item {item_id} not found in inventory."
        return f"Error recording installation: {msg}"

def delete_customer(customer_name: str):
    sb = get_supabase()
    try:
        sb.table("customers").delete().eq("name", customer_name).execute()
    except Exception as e:
        st.error(f"Error deleting customer: {e}")

def delete_customer_installation(installation_id: int):
    """
    Delete a specific installation by its unique ID.
    """
    sb = get_supabase()
    try:
        sb.table("installations").delete().eq("id", int(installation_id)).execute()
        return f"Installation ID {installation_id} deleted successfully."
    except Exception as e:
        return f"Error deleting installation: {e}"

def delete_all_inventory():
    sb = get_supabase()
    try:
        sb.table("items").delete().neq("id", -1).execute()
    except Exception as e:
        st.error(f"Error deleting inventory: {e}")

def delete_all_customers():
    sb = get_supabase()
    try:
        sb.table("installations").delete().neq("id", -1).execute()
        sb.table("customers").delete().neq("id", -1).execute()
    except Exception as e:
        st.error(f"Error deleting customers: {e}")

def add_customer(name: str, phone: str, email: str, address: str) -> str:
    """
    Uppercase handling is done in UI; here we just enforce uniqueness by name.
    """
    sb = get_supabase()
    # Check for existing customer by name
    existing = sb.table("customers").select("id").eq("name", name).limit(1).execute().data
    if existing:
        return f"Customer '{name}' already exists."
    sb.table("customers").insert({"name": name, "phone": phone, "email": email, "address": address}).execute()
    return f"Customer '{name}' added successfully!"

# ---------------- Import / Upsert items from CSV/Excel ----------------
def import_items_and_add_or_insert():
    """
    Console-driven import to mirror your original.
    Expects columns: item (or item_id -> mapped to 'item'), category, unit_cost, selling_price, quantity/stock_quantity, unit (optional)
    """
    import os
    import pandas as pd

    file_path = input("Please enter the full path to your Excel or CSV file: ").strip()
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(file_path)
    elif ext == ".xlsx":
        df = pd.read_excel(file_path, engine="openpyxl")
    elif ext == ".xls":
        df = pd.read_excel(file_path, engine="xlrd")
    else:
        raise ValueError("Unsupported file format. Please upload a CSV or Excel file.")

    def get_col(row, *names, default=None):
        for n in names:
            if n in row and pd.notna(row[n]):
                return row[n]
        return default

    records = []
    for _, row in df.iterrows():
        item_name = get_col(row, "item", "item_id")
        if not item_name:
            continue
        category = str(get_col(row, "category", default="") or "")
        unit_cost = float(get_col(row, "unit_cost", default=0) or 0)
        selling_price = float(get_col(row, "selling_price", default=0) or 0)
        quantity = int(get_col(row, "stock_quantity", "quantity", default=0) or 0)
        unit = get_col(row, "unit", default=None)

        records.append({
            "item": str(item_name),
            "category": category,
            "quantity": quantity,
            "unit_cost": unit_cost,
            "selling_price": selling_price,
            "unit": unit
        })

    if not records:
        print("No rows to import.")
        return

    sb = get_supabase()
    BATCH = 500
    for i in range(0, len(records), BATCH):
        chunk = records[i:i+BATCH]
        sb.table("items").upsert(chunk, on_conflict="item,category").execute()

    print("Items updated or inserted successfully.")