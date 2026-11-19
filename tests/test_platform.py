import http.cookiejar
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import database
import server
from backup import create_backup


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(cls.temp_dir.name) / "venito-test.sqlite3"
        os.environ["ADMIN_USERNAME"] = "test-manager"
        os.environ["ADMIN_PASSWORD"] = "test-password-long-enough"
        database.migrate()
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.VenitoHandler)
        cls.base_url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=3)
        cls.httpd.server_close()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        with database.connect() as db:
            db.execute("DELETE FROM orders")
            db.execute("DELETE FROM customers")
            db.execute("DELETE FROM carts")
            db.execute("DELETE FROM products")
            db.execute("DELETE FROM delivery_areas")
            db.execute("DELETE FROM admin_sessions")
            db.execute("UPDATE working_hours SET opens_at='12:00',closes_at='02:00',active=1")
            db.execute(
                "UPDATE business_settings SET value='1' WHERE key='payment_cash_enabled'"
            )
            db.execute(
                "UPDATE business_settings SET value='0' WHERE key IN "
                "('payment_electronic_enabled','printer_enabled')"
            )
            db.execute("UPDATE business_settings SET value='' WHERE key='printer_host'")
            db.execute("UPDATE business_settings SET value='9100' WHERE key='printer_port'")
        self.csrf = self.login()

    def call(self, method, path, payload=None, csrf=True):
        headers = {"Content-Type": "application/json"}
        if csrf and self.csrf and method in ("POST", "PUT", "DELETE"):
            headers["X-CSRF-Token"] = self.csrf
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            response = self.client.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            status, body = error.code, json.loads(error.read().decode())
            error.close()
            return status, body
        with response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
            return response.status, json.loads(body.decode()) if "json" in content_type else body

    def login(self):
        status, response = self.call(
            "POST",
            "/api/admin/login",
            {"username": "test-manager", "password": "test-password-long-enough"},
            csrf=False,
        )
        self.assertEqual(status, 200)
        return response["csrfToken"]

    def create_product_and_area(self, fee=1500):
        with database.connect() as db:
            category_id = db.execute(
                "SELECT id FROM product_categories WHERE slug='cakes'"
            ).fetchone()["id"]
        status, product = self.call("POST", "/api/admin/products", {
            "name": "كيكة فانيلا", "categoryId": category_id, "price": 12000,
            "description": "كيكة طازجة", "available": True, "featured": True,
            "isNew": True, "images": [],
            "variants": [{"name": "صغيرة", "price": 12000}],
        })
        self.assertEqual(status, 201)
        status, area = self.call("POST", "/api/admin/areas", {
            "name": "المنصور", "district": "karkh", "fee": fee,
        })
        self.assertEqual(status, 201)
        return product["id"], area["id"]

    def fill_cart(self, product_id):
        status, _ = self.call("GET", "/api/cart")
        self.assertEqual(status, 200)
        status, _ = self.call("PUT", "/api/cart", {
            "items": [{"productId": product_id, "quantity": 2}],
        })
        self.assertEqual(status, 200)

    def test_customer_order_uses_database_prices_and_admin_can_update_it(self):
        product_id, area_id = self.create_product_and_area()
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, order = self.call("POST", "/api/orders", {
                "fullName": "سارة أحمد", "phone": "٠٧٨١٢٣٤٥٦٧٨",
                "areaId": area_id, "address": "المنصور، شارع ١٤",
                "paymentMethod": "cash_on_delivery",
            })
        self.assertEqual(status, 201)
        self.assertEqual(order["subtotal"], 24000)
        self.assertEqual(order["deliveryFee"], 1500)
        self.assertEqual(order["total"], 25500)
        self.assertEqual(order["paymentStatus"], "pending")
        status, featured = self.call("GET", "/api/products?group=featured")
        self.assertEqual(status, 200)
        self.assertEqual(featured[0]["name_ar"], "كيكة فانيلا")
        status, popular = self.call("GET", "/api/products?group=bestsellers")
        self.assertEqual(status, 200)
        self.assertEqual(popular[0]["units_sold"], 2)
        status, orders = self.call("GET", "/api/admin/orders")
        self.assertEqual(status, 200)
        self.assertEqual(len(orders), 1)
        status, detail = self.call("GET", f"/api/admin/orders/{orders[0]['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["items"][0]["unit_price_iqd"], 12000)
        status, _ = self.call("PUT", f"/api/admin/orders/{detail['id']}", {
            "status": "preparing",
        })
        self.assertEqual(status, 200)
        status, updated = self.call("GET", f"/api/admin/orders/{detail['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(updated["status"], "preparing")
        self.assertEqual(len(updated["history"]), 2)

    def test_checkout_rejects_missing_delivery_fee_closed_store_and_electronic_payment(self):
        product_id, area_id = self.create_product_and_area(fee=None)
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, response = self.call("POST", "/api/orders", {
                "fullName": "سارة أحمد", "phone": "07812345678",
                "areaId": area_id, "address": "عنوان",
            })
        self.assertEqual(status, 409)
        self.assertIn("أجرة التوصيل", response["error"])
        status, _ = self.call("PUT", f"/api/admin/areas/{area_id}", {
            "name": "المنصور", "district": "karkh", "fee": 1000,
        })
        self.assertEqual(status, 200)
        with mock.patch.object(server, "store_status", return_value=False):
            status, response = self.call("POST", "/api/orders", {
                "fullName": "سارة أحمد", "phone": "07812345678",
                "areaId": area_id, "address": "عنوان",
            })
        self.assertEqual(status, 409)
        self.assertIn("مغلق", response["error"])
        with mock.patch.object(server, "store_status", return_value=True):
            status, response = self.call("POST", "/api/orders", {
                "fullName": "سارة أحمد", "phone": "07812345678",
                "areaId": area_id, "address": "عنوان", "paymentMethod": "electronic",
            })
        self.assertEqual(status, 409)
        self.assertIn("غير متاح", response["error"])

    def test_admin_mutations_require_csrf_token(self):
        status, response = self.call(
            "POST", "/api/admin/areas",
            {"name": "الكرادة", "district": "rusafa", "fee": 1000},
            csrf=False,
        )
        self.assertEqual(status, 403)
        self.assertIn("أمان", response["error"])

    def test_reports_use_real_order_data(self):
        product_id, area_id = self.create_product_and_area()
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, _ = self.call("POST", "/api/orders", {
                "fullName": "عميل التقارير", "phone": "07812345678",
                "areaId": area_id, "address": "عنوان",
            })
        self.assertEqual(status, 201)
        status, report = self.call("GET", "/api/admin/reports?period=day")
        self.assertEqual(status, 200)
        self.assertEqual(report["summary"]["orders"], 1)
        self.assertEqual(report["summary"]["sales"], 24000)
        self.assertEqual(report["summary"]["delivery_fees"], 1500)
        self.assertEqual(report["bestSellers"][0]["quantity"], 2)

    def test_network_printer_test_and_receipt_send_escpos_bytes(self):
        product_id, area_id = self.create_product_and_area()
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, created = self.call("POST", "/api/orders", {
                "fullName": "عميل الاختبار", "phone": "07812345678",
                "areaId": area_id, "address": "بغداد، المنصور",
            })
        self.assertEqual(status, 201)
        with database.connect() as db:
            order_id = db.execute(
                "SELECT id FROM orders WHERE order_number=?", (created["orderNumber"],)
            ).fetchone()["id"]
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(4)
        received = []

        def capture_print_jobs():
            try:
                for _ in range(2):
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(2)
                        chunks = []
                        while True:
                            chunk = connection.recv(4096)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        received.append(b"".join(chunks))
            finally:
                listener.close()

        capture_thread = threading.Thread(target=capture_print_jobs, daemon=True)
        capture_thread.start()
        status, _ = self.call("PUT", "/api/admin/settings", {
            "settings": {
                "printer_enabled": True, "printer_host": "127.0.0.1",
                "printer_port": listener.getsockname()[1], "printer_paper_width": "58",
            },
        })
        self.assertEqual(status, 200)
        status, test_result = self.call("POST", "/api/admin/printer-test", {})
        self.assertEqual(status, 200)
        self.assertIn("اختبار", test_result["message"])
        status, print_result = self.call(
            "POST", f"/api/admin/orders/{order_id}/print", {"target": "receipt"}
        )
        self.assertEqual(status, 200)
        self.assertGreater(print_result["bytesSent"], 0)
        capture_thread.join(timeout=5)
        self.assertEqual(len(received), 2)
        self.assertTrue(received[0].startswith(b"\x1b@"))
        self.assertIn("اختبار الاتصال بالطابعة".encode(), received[0])
        self.assertIn(created["orderNumber"].encode(), received[1])
        self.assertIn(b"\x1dV", received[1])

    def test_working_hours_handle_midnight_in_baghdad(self):
        with database.connect() as db:
            db.execute("UPDATE working_hours SET active=0")
            db.execute(
                "UPDATE working_hours SET opens_at='12:00',closes_at='02:00',active=1 "
                "WHERE weekday=0"
            )
            zone = ZoneInfo("Asia/Baghdad")
            self.assertFalse(server.store_status(db, datetime(2026, 1, 5, 11, 59, tzinfo=zone)))
            self.assertTrue(server.store_status(db, datetime(2026, 1, 5, 12, 0, tzinfo=zone)))
            self.assertTrue(server.store_status(db, datetime(2026, 1, 6, 1, 59, tzinfo=zone)))
            self.assertFalse(server.store_status(db, datetime(2026, 1, 6, 2, 0, tzinfo=zone)))

    def test_working_hours_equal_open_close_is_open_for_that_day(self):
        with database.connect() as db:
            db.execute("UPDATE working_hours SET active=0")
            db.execute(
                "UPDATE working_hours SET opens_at='12:00',closes_at='12:00',active=1 "
                "WHERE weekday=0"
            )
            zone = ZoneInfo("Asia/Baghdad")
            self.assertTrue(server.store_status(db, datetime(2026, 1, 5, 0, 0, tzinfo=zone)))
            self.assertTrue(server.store_status(db, datetime(2026, 1, 5, 23, 59, tzinfo=zone)))
            self.assertFalse(server.store_status(db, datetime(2026, 1, 6, 12, 0, tzinfo=zone)))

    def test_public_pages_and_health_endpoint_are_served(self):
        status, health = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        status, page = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("حلويات ومعجنات فينيتو".encode(), page)
        status, admin = self.call("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn("الدخول".encode(), admin)

    def test_backup_is_a_readable_sqlite_snapshot(self):
        backup_path = create_backup(Path(self.temp_dir.name) / "backup.sqlite3")
        import sqlite3
        snapshot = sqlite3.connect(backup_path)
        try:
            self.assertEqual(
                snapshot.execute("SELECT COUNT(*) FROM product_categories").fetchone()[0],
                7,
            )
        finally:
            snapshot.close()


if __name__ == "__main__":
    unittest.main()
