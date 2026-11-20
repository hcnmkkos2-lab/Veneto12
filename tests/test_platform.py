import base64
import contextlib
import hashlib
import io
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

from PIL import Image

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
            db.execute("DELETE FROM admin_sessions")
            db.execute("DELETE FROM business_assets")
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

    def test_admin_login_uses_password_and_opens_dashboard_without_email(self):
        with database.connect() as db:
            original_hash = db.execute(
                "SELECT password_hash FROM staff_users WHERE username='test-manager'"
            ).fetchone()["password_hash"]
        status, _ = self.call("POST", "/api/admin/logout", {})
        self.assertEqual(status, 200)
        self.csrf = ""
        status, _ = self.call("POST", "/api/admin/login", {
            "username": "test-manager", "password": "incorrect-password",
        }, csrf=False)
        self.assertEqual(status, 401)
        status, _ = self.call("GET", "/api/admin/session")
        self.assertEqual(status, 401)
        status, logged_in = self.call("POST", "/api/admin/login", {
            "username": "test-manager", "password": "test-password-long-enough",
        }, csrf=False)
        self.assertEqual(status, 200)
        self.assertEqual(logged_in["user"]["username"], "test-manager")
        self.assertNotIn("otpRequired", logged_in)
        self.csrf = logged_in["csrfToken"]
        status, session = self.call("GET", "/api/admin/session")
        self.assertEqual(status, 200)
        self.assertEqual(session["user"]["username"], "test-manager")
        self.assertEqual(session["csrfToken"], logged_in["csrfToken"])
        status, _ = self.call("GET", "/api/admin/summary")
        self.assertEqual(status, 200)
        with database.connect() as db:
            self.assertEqual(db.execute(
                "SELECT password_hash FROM staff_users WHERE username='test-manager'"
            ).fetchone()["password_hash"], original_hash)

    def create_product_and_area(self, fee=1500):
        with database.connect() as db:
            category_id = db.execute(
                "SELECT id FROM product_categories WHERE slug='sweets'"
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
        with database.connect() as db:
            saved_order = db.execute(
                "SELECT delivery_area_id,delivery_area_name,delivery_fee_iqd,"
                "delivery_fee_determined,total_iqd FROM orders WHERE order_number=?",
                (order["orderNumber"],),
            ).fetchone()
        self.assertEqual(saved_order["delivery_area_id"], area_id)
        self.assertEqual(saved_order["delivery_area_name"], "المنصور")
        self.assertEqual(saved_order["delivery_fee_iqd"], 1500)
        self.assertEqual(saved_order["delivery_fee_determined"], 1)
        self.assertEqual(saved_order["total_iqd"], 25500)
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

    def test_checkout_saves_unknown_fee_without_charging_and_rejects_closed_store(self):
        product_id, area_id = self.create_product_and_area(fee=None)
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, order = self.call("POST", "/api/orders", {
                "fullName": "سارة أحمد", "phone": "07812345678",
                "areaId": area_id, "address": "عنوان",
            })
        self.assertEqual(status, 201)
        self.assertEqual(order["subtotal"], 24000)
        self.assertIsNone(order["deliveryFee"])
        self.assertIsNone(order["total"])
        self.assertFalse(order["deliveryFeeDetermined"])
        with database.connect() as db:
            saved = db.execute(
                "SELECT id,delivery_fee_iqd,delivery_fee_determined,subtotal_iqd,total_iqd "
                "FROM orders WHERE order_number=?", (order["orderNumber"],)
            ).fetchone()
            self.assertEqual(saved["delivery_fee_iqd"], 0)
            self.assertEqual(saved["delivery_fee_determined"], 0)
            self.assertEqual(saved["total_iqd"], saved["subtotal_iqd"])
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM payment_transactions WHERE order_id=?", (saved["id"],)
            ).fetchone()[0], 0)
        status, admin_order = self.call("GET", f"/api/admin/orders/{saved['id']}")
        self.assertEqual(status, 200)
        self.assertIsNone(admin_order["delivery_fee_iqd"])
        self.assertIsNone(admin_order["total_iqd"])
        status, admin_orders = self.call("GET", "/api/admin/orders")
        self.assertEqual(status, 200)
        self.assertIsNone(admin_orders[0]["delivery_fee_iqd"])
        self.assertIsNone(admin_orders[0]["total_iqd"])
        status, report = self.call("GET", "/api/admin/reports?period=day")
        self.assertEqual(status, 200)
        self.assertEqual(report["summary"]["sales"], 24000)
        self.assertEqual(report["summary"]["delivery_fees"], 0)
        status, _ = self.call("PUT", f"/api/admin/areas/{area_id}", {
            "name": "المنصور", "district": "karkh", "fee": 1000,
        })
        self.assertEqual(status, 200)
        self.fill_cart(product_id)
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

    def test_baghdad_delivery_areas_have_only_the_specified_fees(self):
        status, areas = self.call("GET", "/api/areas")
        self.assertEqual(status, 200)
        fees = {area["name_ar"]: area["fee_iqd"] for area in areas}
        self.assertEqual(fees["مدينة الصدر"], 2000)
        self.assertEqual(fees["البنوك"], 1000)
        self.assertEqual(fees["الشعب"], 1000)
        self.assertEqual(fees["باب المعظم"], 3000)
        self.assertGreaterEqual(len(areas), 60)
        for name in (
            "الحرية", "المنصور", "حي أور", "الشرطة الرابعة", "الشرطة الثانية",
            "الشعلة", "الغزالية", "شارع فلسطين",
        ):
            self.assertIsNone(fees[name])

    def test_delivery_areas_remain_listed_when_delivery_is_disabled(self):
        with database.connect() as db:
            original = db.execute(
                "SELECT value FROM business_settings WHERE key='delivery_enabled'"
            ).fetchone()["value"]
            db.execute(
                "UPDATE business_settings SET value='0' WHERE key='delivery_enabled'"
            )
        try:
            status, areas = self.call("GET", "/api/areas")
            self.assertEqual(status, 200)
            self.assertGreaterEqual(len(areas), 60)
            self.assertIn("الحرية", {area["name_ar"] for area in areas})
            self.assertEqual(
                {area["name_ar"]: area["fee_iqd"] for area in areas}["مدينة الصدر"],
                2000,
            )
            with mock.patch.object(server, "store_status", return_value=True):
                status, response = self.call("POST", "/api/orders", {
                    "fullName": "سارة أحمد", "phone": "07812345678",
                    "areaId": areas[0]["id"], "address": "عنوان",
                })
            self.assertEqual(status, 409)
            self.assertIn("التوصيل غير متاح", response["error"])
        finally:
            with database.connect() as db:
                db.execute(
                    "UPDATE business_settings SET value=? WHERE key='delivery_enabled'",
                    (original,),
                )

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

    def test_dashboard_and_order_filters_use_database_records(self):
        product_id, area_id = self.create_product_and_area()
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, created = self.call("POST", "/api/orders", {
                "fullName": "عميل لوحة الإدارة", "phone": "07812345678",
                "areaId": area_id, "address": "عنوان الاختبار",
            })
        self.assertEqual(status, 201)
        today = datetime.now(ZoneInfo("Asia/Baghdad")).date().isoformat()
        status, summary = self.call("GET", "/api/admin/summary")
        self.assertEqual(status, 200)
        self.assertEqual(summary["totalOrders"], 1)
        self.assertEqual(summary["newOrders"], 1)
        self.assertEqual(summary["pendingOrders"], 1)
        self.assertEqual(summary["todaySales"], 24000)
        self.assertEqual(summary["monthlySales"], 24000)
        self.assertEqual(len(summary["salesChart"]), 14)

        status, orders = self.call(
            "GET",
            f"/api/admin/orders?q={created['orderNumber']}&status=pending"
            f"&areaId={area_id}&dateFrom={today}&dateTo={today}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["order_number"], created["orderNumber"])
        status, report = self.call(
            "GET", f"/api/admin/reports?dateFrom={today}&dateTo={today}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(report["summary"]["sales"], 24000)
        self.assertEqual(report["summary"]["delivery_fees"], 1500)
        self.assertEqual(report["summary"]["completed"], 0)

    def test_checkout_generates_private_arabic_pdf_receipt_for_customer_and_admin(self):
        image_buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (160, 110, 75)).save(image_buffer, format="PNG")
        image_data = "data:image/png;base64," + base64.b64encode(
            image_buffer.getvalue()
        ).decode("ascii")
        status, _ = self.call("PUT", "/api/admin/logo", {"imageData": image_data})
        self.assertEqual(status, 200)

        product_id, area_id = self.create_product_and_area()
        self.fill_cart(product_id)
        with mock.patch.object(server, "store_status", return_value=True):
            status, order = self.call("POST", "/api/orders", {
                "fullName": "سارة أحمد", "phone": "07812345678",
                "areaId": area_id, "address": "المنصور، بغداد",
            })
        self.assertEqual(status, 201)
        self.assertRegex(order["receiptNumber"], r"^VR-[0-9]{6}-[A-F0-9]{16}$")
        self.assertRegex(order["receiptUrl"], r"^/receipt/[A-Za-z0-9_-]{43}\.pdf$")
        token = order["receiptUrl"].split("/")[-1].removesuffix(".pdf")
        with database.connect() as db:
            stored = db.execute(
                "SELECT receipt_number,token_hash,pdf_data FROM receipts WHERE order_id="
                "(SELECT id FROM orders WHERE order_number=?)",
                (order["orderNumber"],),
            ).fetchone()
        self.assertEqual(stored["receipt_number"], order["receiptNumber"])
        self.assertEqual(stored["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token.encode(), stored["pdf_data"])
        self.assertTrue(stored["pdf_data"].startswith(b"%PDF-"))
        self.assertIn(b"/FontFile2", stored["pdf_data"])

        customer = urllib.request.build_opener()
        receipt_logs = io.StringIO()
        with contextlib.redirect_stdout(receipt_logs):
            with customer.open(self.base_url + order["receiptUrl"], timeout=5) as response:
                self.assertEqual(response.headers.get_content_type(), "application/pdf")
                self.assertIn("attachment", response.headers["Content-Disposition"])
                customer_pdf = response.read()
            with self.assertRaises(urllib.error.HTTPError) as invalid_receipt:
                customer.open(
                    self.base_url + "/receipt/" + ("A" * 43) + ".pdf", timeout=5
                )
            self.assertEqual(invalid_receipt.exception.code, 404)
            invalid_receipt.exception.close()
        self.assertEqual(customer_pdf, stored["pdf_data"])
        self.assertNotIn(token, receipt_logs.getvalue())
        self.assertNotIn("A" * 43, receipt_logs.getvalue())

        order_id = self.call("GET", "/api/admin/orders")[1][0]["id"]
        status, admin_pdf = self.call("GET", f"/api/admin/orders/{order_id}/receipt")
        self.assertEqual(status, 200)
        self.assertEqual(admin_pdf, stored["pdf_data"])
        status, detail = self.call("GET", f"/api/admin/orders/{order_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["receipt_number"], order["receiptNumber"])

    def test_uploaded_product_images_are_saved_and_preserved_on_edit(self):
        image_buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (180, 125, 80)).save(image_buffer, format="PNG")
        image_data = "data:image/png;base64," + base64.b64encode(
            image_buffer.getvalue()
        ).decode("ascii")
        with database.connect() as db:
            category_id = db.execute(
                "SELECT id FROM product_categories WHERE slug='sweets'"
            ).fetchone()["id"]
        status, created = self.call("POST", "/api/admin/products", {
            "name": "صورة اختبار", "categoryId": category_id, "price": 1000,
            "images": [], "imageData": image_data,
        })
        self.assertEqual(status, 201)
        status, products = self.call("GET", "/api/admin/products")
        self.assertEqual(status, 200)
        product = next(item for item in products if item["id"] == created["id"])
        image_url = product["images"][0]
        self.assertRegex(image_url, r"^/api/product-images/[0-9]+$")
        status, image = self.call("GET", image_url)
        self.assertEqual(status, 200)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))

        status, _ = self.call("PUT", f"/api/admin/products/{created['id']}", {
            "name": "صورة اختبار بعد التعديل", "categoryId": category_id,
            "price": 1000, "description": "", "available": True,
            "variants": [],
        })
        self.assertEqual(status, 200)
        status, products = self.call("GET", "/api/admin/products")
        product = next(item for item in products if item["id"] == created["id"])
        self.assertEqual(product["images"], [image_url])
        status, image = self.call("GET", image_url)
        self.assertEqual(status, 200)

        status, _ = self.call("DELETE", f"/api/admin/products/{created['id']}", {})
        self.assertEqual(status, 200)
        status, _ = self.call("GET", image_url)
        self.assertEqual(status, 404)

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

    def test_working_hours_roll_over_week_and_normalize_aware_time(self):
        with database.connect() as db:
            db.execute("UPDATE working_hours SET active=0")
            db.execute(
                "UPDATE working_hours SET opens_at='12:00',closes_at='02:00',active=1 "
                "WHERE weekday=6"
            )
            baghdad = ZoneInfo("Asia/Baghdad")
            self.assertTrue(server.store_status(db, datetime(2026, 1, 4, 23, 59, tzinfo=baghdad)))
            self.assertTrue(server.store_status(db, datetime(2026, 1, 4, 22, 0, tzinfo=ZoneInfo("UTC"))))
            self.assertTrue(server.store_status(db, datetime(2026, 1, 5, 1, 59, tzinfo=baghdad)))
            self.assertFalse(server.store_status(db, datetime(2026, 1, 5, 2, 0, tzinfo=baghdad)))
            self.assertTrue(server.store_status(db, datetime(2026, 1, 4, 23, 59)))

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
        self.assertIn("حلويات ومعجنات فينتو".encode(), page)
        self.assertIn(b"VENTO", page)
        self.assertIn(b'id="product-dialog"', page)
        self.assertIn(b'id="area-select-cart"', page)
        status, categories = self.call("GET", "/api/categories")
        self.assertEqual(status, 200)
        self.assertEqual(len(categories), 3)
        self.assertIn("الحلويات", [category["name_ar"] for category in categories])
        self.assertIn("المعجنات والكيك", [category["name_ar"] for category in categories])
        self.assertIn("ورق عنب", [category["name_ar"] for category in categories])
        status, admin = self.call("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn("الدخول".encode(), admin)

    def test_startup_does_not_create_products_with_sample_prices(self):
        database.migrate()
        with database.connect() as db:
            products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        self.assertEqual(products, 0)

    def test_backup_is_a_readable_sqlite_snapshot(self):
        backup_path = create_backup(Path(self.temp_dir.name) / "backup.sqlite3")
        import sqlite3
        snapshot = sqlite3.connect(backup_path)
        try:
            self.assertEqual(
                snapshot.execute("SELECT COUNT(*) FROM product_categories").fetchone()[0],
                3,
            )
        finally:
            snapshot.close()


if __name__ == "__main__":
    unittest.main()
