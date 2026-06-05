"""Google Sheets integration for stock and orders management."""

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsDB:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self._ensure_worksheets()

    def _ensure_worksheets(self):
        """Create Stock and Orders sheets if they don't exist."""
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if "Stock" not in existing:
            ws = self.spreadsheet.add_worksheet(title="Stock", rows=100, cols=7)
            ws.append_row(["Name", "Style", "ABV", "IBU", "Bottles", "Price", "Available"])
        self.stock_sheet = self.spreadsheet.worksheet("Stock")

        if "Orders" not in existing:
            ws = self.spreadsheet.add_worksheet(title="Orders", rows=500, cols=7)
            ws.append_row(["Order ID", "Date", "User", "Username", "Item", "Qty", "Status"])
        self.orders_sheet = self.spreadsheet.worksheet("Orders")

    def get_stock(self) -> list[dict]:
        """Return all stock items that are available."""
        records = self.stock_sheet.get_all_records()
        return [r for r in records if str(r.get("Available", "")).lower() in ("yes", "1", "true", "+")]

    def get_all_stock(self) -> list[dict]:
        """Return all stock items including unavailable."""
        return self.stock_sheet.get_all_records()

    def add_stock_item(self, name: str, style: str, abv: str, ibu: str, qty_bottles: str, price: str):
        """Add a new item to stock."""
        self.stock_sheet.append_row([name, style, abv, ibu, qty_bottles, price, "Yes"])

    def remove_stock_item(self, name: str) -> bool:
        """Mark an item as unavailable by name."""
        records = self.stock_sheet.get_all_records()
        for i, r in enumerate(records, start=2):  # row 1 is header
            if r["Name"].lower() == name.lower():
                self.stock_sheet.update_cell(i, 7, "No")
                return True
        return False

    def update_stock_qty(self, name: str, new_qty: str) -> bool:
        """Update bottle count for an item."""
        records = self.stock_sheet.get_all_records()
        for i, r in enumerate(records, start=2):
            if r["Name"].lower() == name.lower():
                self.stock_sheet.update_cell(i, 5, new_qty)
                return True
        return False

    def place_order(self, order_id: str, date: str, user_fullname: str, username: str, item: str, qty: int):
        """Record a new order."""
        self.orders_sheet.append_row([order_id, date, user_fullname, username, item, qty, "New"])

    def get_orders_by_user(self, username: str) -> list[dict]:
        """Get all orders for a specific user."""
        records = self.orders_sheet.get_all_records()
        return [r for r in records if r.get("Username") == username]
