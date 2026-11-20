import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("VENITO_DATABASE", ROOT / "data" / "venito.sqlite3"))


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exception_type, exception_value, traceback):
        try:
            return super().__exit__(exception_type, exception_value, traceback)
        finally:
            self.close()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        DATABASE_PATH, timeout=10, factory=ClosingConnection
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def migrate():
    with connect() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["version"]
            for row in db.execute("SELECT version FROM schema_migrations")
        }
        for migration in sorted((ROOT / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
            version = int(migration.name.split("_", 1)[0])
            if version in applied:
                continue
            db.executescript(migration.read_text(encoding="utf-8"))
            db.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utc_now()),
            )

        defaults = {
            "business_name": "VENTO",
            "business_name_ar": "حلويات ومعجنات فينتو",
            "phone": "",
            "address": "بغداد، العراق",
            "instagram_url": "",
            "facebook_url": "",
            "currency": "IQD",
            "store_enabled": "1",
            "delivery_enabled": "1",
            "receipt_footer": "",
            "payment_cash_enabled": "1",
            "payment_electronic_enabled": "0",
            "printer_enabled": "0",
            "printer_host": "",
            "printer_port": "9100",
            "printer_paper_width": "58",
        }
        db.executemany(
            "INSERT OR IGNORE INTO business_settings (key, value) VALUES (?, ?)",
            defaults.items(),
        )
        db.executemany(
            "INSERT OR IGNORE INTO working_hours (weekday, opens_at, closes_at, active) "
            "VALUES (?, '12:00', '02:00', 1)",
            ((day,) for day in range(7)),
        )
        categories = (
            ("الكيك والتورتات", "cakes", 1),
            ("المعجنات والفطائر", "pastries", 2),
            ("كرواسون", "croissants", 3),
            ("كوكيز", "cookies", 4),
            ("الحلويات الشرقية", "arabic-sweets", 5),
            ("الحلويات الغربية", "western-desserts", 6),
            ("بوكسات المناسبات", "special-occasions", 7),
            ("أطباق الضيافة", "hospitality-trays", 8),
            ("الشوكولاتة", "chocolate", 9),
        )
        db.executemany(
            "INSERT OR IGNORE INTO product_categories (name_ar, slug, sort_order, created_at) "
            "VALUES (?, ?, ?, ?)",
            ((*category, utc_now()) for category in categories),
        )
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if username and password and (
            len(username) < 3 or len(username) > 80 or not username.isascii()
            or not all(char.isalnum() or char in "_.-" for char in username)
        ):
            raise ValueError("ADMIN_USERNAME must be 3-80 ASCII letters, digits, dot, dash or underscore.")
        if username and password and len(password) < 12:
            raise ValueError("ADMIN_PASSWORD must be at least 12 characters.")
        if username and password and not db.execute(
            "SELECT 1 FROM staff_users WHERE username = ?", (username,)
        ).fetchone():
            salt = secrets.token_bytes(16)
            password_hash = salt.hex() + hashlib.scrypt(
                password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
            ).hex()
            db.execute(
                "INSERT INTO staff_users (username, password_hash, role, created_at) "
                "VALUES (?, ?, 'admin', ?)",
                (username, password_hash, utc_now()),
            )
