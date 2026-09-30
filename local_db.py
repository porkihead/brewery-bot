"""Local JSON-based storage fallback (no Google Sheets needed)."""

import json
import os

DATA_FILE = os.environ.get("DATA_FILE_PATH", os.path.join(os.path.dirname(__file__), "data.json"))
SEED_FILE = os.path.join(os.path.dirname(__file__), "data.json")


def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        # First run with volume: seed from bundled data.json
        if DATA_FILE != SEED_FILE and os.path.exists(SEED_FILE):
            import shutil
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            shutil.copy2(SEED_FILE, DATA_FILE)
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"stock": [], "orders": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class LocalDB:
    def get_stock(self) -> list[dict]:
        data = _load()
        return [item for item in data["stock"] if item.get("Available", "").lower() in ("yes", "1", "true", "+")]

    def get_all_stock(self) -> list[dict]:
        return _load()["stock"]

    def add_stock_item(self, name: str, style: str, abv: str, ibu: str, qty_bottles: str, price: str):
        data = _load()
        data["stock"].append({
            "Name": name,
            "Style": style,
            "ABV": abv,
            "IBU": ibu,
            "Bottles": qty_bottles,
            "Price": price,
            "Available": "Yes",
        })
        _save(data)

    def remove_stock_item(self, name: str) -> bool:
        data = _load()
        for item in data["stock"]:
            if item["Name"].lower() == name.lower():
                item["Available"] = "No"
                _save(data)
                return True
        return False

    def update_stock_qty(self, name: str, new_qty: str) -> bool:
        data = _load()
        for item in data["stock"]:
            if item["Name"].lower() == name.lower():
                item["Bottles"] = new_qty
                _save(data)
                return True
        return False

    def place_order(self, order_id: str, date: str, user_fullname: str, username: str, item: str, qty: int):
        data = _load()
        data["orders"].append({
            "Order ID": order_id,
            "Date": date,
            "User": user_fullname,
            "Username": username,
            "Item": item,
            "Qty": qty,
            "Status": "Нове",
        })
        _save(data)

    def get_orders_by_user(self, username: str) -> list[dict]:
        data = _load()
        return [o for o in data["orders"] if o.get("Username") == username]

    def get_all_orders(self, status: str = None) -> list[dict]:
        data = _load()
        if status:
            return [o for o in data["orders"] if o.get("Status", "").lower() == status.lower()]
        return data["orders"]

    def get_data_file_path(self) -> str:
        return DATA_FILE
