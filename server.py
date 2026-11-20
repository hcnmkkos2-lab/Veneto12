import base64
import binascii
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import socket
import sqlite3
import time
import textwrap
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.sax.saxutils import escape
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

import arabic_reshaper
import database
from PIL import Image as PILImage
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
TIMEZONE = ZoneInfo("Asia/Baghdad")
STATUSES = {
    "new": "طلب جديد",
    "confirmed": "تم تأكيد الطلب",
    "preparing": "قيد التحضير",
    "ready": "جاهز للتوصيل",
    "out_for_delivery": "خرج للتوصيل",
    "delivered": "تم التوصيل",
    "cancelled": "ملغي",
}
DISTRICTS = {"karkh": "الكرخ", "rusafa": "الرصافة"}
PHONE_RE = re.compile(r"^[0-9]{7,15}$")
MAX_BODY = 1_000_000
MAX_IMAGE_BYTES = 600 * 1024
LOGIN_ATTEMPTS = {}
RECEIPT_FONT = "VentoArabic"
pdfmetrics.registerFont(TTFont(RECEIPT_FONT, str(ROOT / "assets" / "fonts" / "DejaVuSans.ttf")))


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def fail(message, status=400):
    raise APIError(status, message)


def normalize_phone(value):
    digits = str(value or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    return re.sub(r"[\s()+-]", "", digits)


def get_setting(db, key, default=""):
    row = db.execute(
        "SELECT value FROM business_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def set_setting(db, key, value):
    db.execute(
        "INSERT INTO business_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def store_status(db, now=None):
    if get_setting(db, "store_enabled", "1") != "1":
        return False
    if now is None:
        local_now = datetime.now(TIMEZONE)
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=TIMEZONE)
    else:
        local_now = now.astimezone(TIMEZONE)
    minute = local_now.hour * 60 + local_now.minute
    weekday = local_now.weekday()
    hours = db.execute("SELECT * FROM working_hours ORDER BY weekday").fetchall()
    for row in hours:
        if not row["active"]:
            continue
        opening_text = str(row["opens_at"] or "")
        closing_text = str(row["closes_at"] or "")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", opening_text):
            continue
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", closing_text):
            continue
        opening = int(opening_text[:2]) * 60 + int(opening_text[3:])
        closing = int(closing_text[:2]) * 60 + int(closing_text[3:])
        if opening == closing:
            is_open = weekday == row["weekday"]
        elif closing < opening:
            is_open = (
                weekday == row["weekday"] and minute >= opening
            ) or (
                (weekday - 1) % 7 == row["weekday"] and minute < closing
            )
        else:
            is_open = weekday == row["weekday"] and opening <= minute < closing
        if is_open:
            return True
    return False


def require_text(data, key, label, maximum=200):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        fail(f"يرجى إدخال {label} بشكل صحيح.")
    return value.strip()


def bool_value(value):
    return 1 if value in (True, 1, "1", "true", "on") else 0


def safe_int(value, label, minimum=0, maximum=10**9):
    if isinstance(value, bool):
        fail(f"قيمة {label} غير صحيحة.")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        fail(f"قيمة {label} غير صحيحة.")
    if parsed < minimum or parsed > maximum:
        fail(f"قيمة {label} خارج النطاق المسموح.")
    return parsed


def row_dict(row):
    return dict(row) if row is not None else None


def decode_image_data(value):
    if not isinstance(value, str) or len(value) > MAX_IMAGE_BYTES * 4 // 3 + 128:
        fail("حجم الصورة أكبر من الحد المسموح.")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})", value)
    if not match:
        fail("صيغة الصورة غير مدعومة. استخدموا PNG أو JPEG.")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error):
        fail("بيانات الصورة غير صحيحة.")
    if len(content) > MAX_IMAGE_BYTES:
        fail("حجم الصورة يجب ألا يتجاوز 600 كيلوبايت.")
    mime_type = f"image/{match.group(1)}"
    if (mime_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n")) or (
        mime_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff")
    ):
        fail("محتوى الصورة لا يطابق نوع الملف.")
    try:
        with PILImage.open(io.BytesIO(content)) as image:
            expected_format = "PNG" if mime_type == "image/png" else "JPEG"
            if image.format != expected_format or image.width * image.height > 30_000_000:
                fail("أبعاد الصورة أو نوعها غير مدعوم.")
            image.verify()
    except (OSError, ValueError, PILImage.DecompressionBombError):
        fail("ملف الصورة تالف أو غير مدعوم.")
    return content, mime_type


def _rtl(text):
    return get_display(arabic_reshaper.reshape(str(text)))


def _receipt_paragraph(text, style):
    return Paragraph(escape(_rtl(text)), style)


def build_receipt_pdf(order, items, receipt_number, business_name, phone, address, footer, logo=None):
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=12 * mm,
        title=f"VENTO {receipt_number}",
        author=business_name,
    )
    styles = {
        "logo": ParagraphStyle(
            "receiptLogo", fontName=RECEIPT_FONT, fontSize=25, leading=28,
            alignment=TA_CENTER, textColor=colors.HexColor("#9a6947"),
        ),
        "title": ParagraphStyle(
            "receiptTitle", fontName=RECEIPT_FONT, fontSize=14, leading=19,
            alignment=TA_CENTER, textColor=colors.HexColor("#4a281f"),
        ),
        "center": ParagraphStyle(
            "receiptCenter", fontName=RECEIPT_FONT, fontSize=8, leading=12,
            alignment=TA_CENTER, textColor=colors.HexColor("#66574b"),
        ),
        "body": ParagraphStyle(
            "receiptBody", fontName=RECEIPT_FONT, fontSize=8, leading=12,
            alignment=TA_RIGHT, textColor=colors.HexColor("#35241f"),
        ),
        "small": ParagraphStyle(
            "receiptSmall", fontName=RECEIPT_FONT, fontSize=7, leading=10,
            alignment=TA_RIGHT, textColor=colors.HexColor("#75675b"),
        ),
        "table": ParagraphStyle(
            "receiptTable", fontName=RECEIPT_FONT, fontSize=7, leading=10,
            alignment=TA_RIGHT, textColor=colors.HexColor("#35241f"),
        ),
        "tableCenter": ParagraphStyle(
            "receiptTableCenter", fontName=RECEIPT_FONT, fontSize=7, leading=10,
            alignment=TA_CENTER, textColor=colors.HexColor("#35241f"),
        ),
    }

    story = []
    if logo:
        image_reader = ImageReader(io.BytesIO(logo))
        image_width, image_height = image_reader.getSize()
        scale = min(23 * mm / image_width, 23 * mm / image_height)
        story.append(Image(
            io.BytesIO(logo), width=image_width * scale, height=image_height * scale,
            hAlign="CENTER",
        ))
    else:
        story.append(_receipt_paragraph("V", styles["logo"]))
    story.extend([
        _receipt_paragraph(business_name, styles["title"]),
        _receipt_paragraph(phone, styles["center"]) if phone else Spacer(1, 1),
        _receipt_paragraph(address, styles["center"]) if address else Spacer(1, 1),
        Spacer(1, 4 * mm),
    ])

    created = datetime.fromisoformat(order["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created_text = created.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    details = [
        [_receipt_paragraph(f"رقم الإيصال: {receipt_number}", styles["body"])],
        [_receipt_paragraph(f"رقم الطلب: {order['order_number']}", styles["body"])],
        [_receipt_paragraph(f"التاريخ والوقت: {created_text}", styles["body"])],
        [_receipt_paragraph(f"العميل: {order['full_name']}", styles["body"])],
        [_receipt_paragraph(f"الهاتف: {order['phone']}", styles["body"])],
        [_receipt_paragraph(
            f"منطقة التوصيل: {order['delivery_area_name']} — {order['delivery_address']}",
            styles["body"],
        )],
    ]
    story.append(Table(details, colWidths=[document.width], hAlign="RIGHT", style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ])))
    story.append(Spacer(1, 4 * mm))

    item_rows = [[
        _receipt_paragraph("المنتج", styles["table"]),
        _receipt_paragraph("الكمية", styles["tableCenter"]),
        _receipt_paragraph("سعر القطعة", styles["tableCenter"]),
        _receipt_paragraph("الإجمالي", styles["tableCenter"]),
    ]]
    for item in items:
        name = f"{item['product_name_ar']} {item['variant_name_ar']}".strip()
        item_rows.append([
            _receipt_paragraph(name, styles["table"]),
            _receipt_paragraph(item["quantity"], styles["tableCenter"]),
            _receipt_paragraph(f"{item['unit_price_iqd']:,} د.ع", styles["tableCenter"]),
            _receipt_paragraph(f"{item['line_total_iqd']:,} د.ع", styles["tableCenter"]),
        ])
    item_table = Table(item_rows, colWidths=[
        document.width - 57 * mm, 13 * mm, 22 * mm, 22 * mm,
    ], repeatRows=1, hAlign="RIGHT")
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe5d8")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2d7ca")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 4 * mm))

    delivery = f"{order['delivery_fee_iqd']:,} د.ع" if order["delivery_fee_determined"] else "يحدد لاحقاً"
    total = f"{order['total_iqd']:,} د.ع" if order["delivery_fee_determined"] else "يحدد لاحقاً"
    totals = [
        [_receipt_paragraph("المجموع الفرعي", styles["body"]),
         _receipt_paragraph(f"{order['subtotal_iqd']:,} د.ع", styles["body"])],
        [_receipt_paragraph("أجرة التوصيل", styles["body"]),
         _receipt_paragraph(delivery, styles["body"])],
        [_receipt_paragraph("الإجمالي النهائي", styles["title"]),
         _receipt_paragraph(total, styles["title"])],
        [_receipt_paragraph(
            f"طريقة الدفع: {'نقداً عند الاستلام' if order['payment_method'] == 'cash_on_delivery' else 'إلكتروني'}",
            styles["small"],
        )],
    ]
    totals_table = Table(totals, colWidths=[document.width * 0.55, document.width * 0.45], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("SPAN", (0, 3), (1, 3)),
        ("LINEABOVE", (0, 2), (-1, 2), 0.7, colors.HexColor("#b28a66")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(totals_table)
    if order["delivery_instructions"]:
        story.extend([
            Spacer(1, 2 * mm),
            _receipt_paragraph(f"ملاحظات التوصيل: {order['delivery_instructions']}", styles["small"]),
        ])
    if footer:
        story.extend([Spacer(1, 5 * mm), _receipt_paragraph(footer, styles["center"])])
    document.build(story)
    return buffer.getvalue()


def order_dict(row):
    result = row_dict(row)
    if result and not result.get("delivery_fee_determined", 1):
        result["delivery_fee_iqd"] = None
        result["total_iqd"] = None
    return result


class VenitoHandler(BaseHTTPRequestHandler):
    server_version = "VENTO/1.0"

    def log_message(self, format_string, *args):
        message = format_string % args
        if urlparse(self.path).path.startswith("/receipt/"):
            message = message.replace(self.path, "/receipt/[redacted].pdf")
        print("%s - %s" % (self.address_string(), message))

    def _send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https:; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        for key, value in (headers or {}).items():
            values = value if isinstance(value, (list, tuple)) else (value,)
            for header_value in values:
                self.send_header(key, header_value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload, headers=None):
        self._send(status, payload, headers=headers)

    def _cookie(self, name):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            morsel = cookie.get(name)
            return morsel.value if morsel else ""
        except Exception:
            return ""

    def _set_cookie(self, name, value, max_age, http_only=True, same_site="Lax"):
        secure = "; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""
        http_only_part = "; HttpOnly" if http_only else ""
        return (
            f"{name}={value}; Path=/; Max-Age={max_age}; SameSite={same_site}"
            f"{http_only_part}{secure}"
        )

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            fail("حجم الطلب غير صحيح.")
        if length < 0 or length > MAX_BODY:
            fail("حجم الطلب أكبر من الحد المسموح.", 413)
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            fail("صيغة البيانات غير صحيحة.")
        if not isinstance(value, dict):
            fail("صيغة البيانات غير صحيحة.")
        return value

    def _origin_check(self):
        origin = self.headers.get("Origin")
        if origin:
            if urlparse(origin).netloc != self.headers.get("Host"):
                fail("مصدر الطلب غير مسموح.", 403)

    def _admin(self, mutation=False, roles=None):
        token = self._cookie("venito_admin")
        if not token:
            fail("يرجى تسجيل الدخول للمتابعة.", 401)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with database.connect() as db:
            session = db.execute(
                "SELECT s.csrf_token, u.id, u.username, u.role, u.active "
                "FROM admin_sessions s JOIN staff_users u ON u.id=s.staff_user_id "
                "WHERE s.token_hash=? AND s.expires_at>?",
                (digest, database.utc_now()),
            ).fetchone()
        if not session or not session["active"]:
            fail("انتهت الجلسة. يرجى تسجيل الدخول مجدداً.", 401)
        if mutation:
            self._origin_check()
            if not hmac.compare_digest(
                self.headers.get("X-CSRF-Token", ""), session["csrf_token"]
            ):
                fail("تعذر التحقق من أمان الطلب. حدّث الصفحة وحاول مجدداً.", 403)
        if roles and session["role"] not in roles:
            fail("ليست لديك صلاحية تنفيذ هذا الإجراء.", 403)
        return session

    def _cart(self, db, create=True):
        token = self._cookie("venito_cart")
        if token:
            row = db.execute(
                "SELECT id FROM carts WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            if row:
                return row["id"], None
        if not create:
            return None, None
        token = secrets.token_urlsafe(32)
        cursor = db.execute(
            "INSERT INTO carts (token_hash, updated_at) VALUES (?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), database.utc_now()),
        )
        return cursor.lastrowid, self._set_cookie("venito_cart", token, 60 * 60 * 24 * 30)

    def _dispatch(self):
        path = unquote(urlparse(self.path).path)
        method = self.command
        if path == "/api/health" and method == "GET":
            return self._json(200, {"ok": True})
        if path.startswith("/receipt/") and method == "GET":
            return self._public_receipt(path)
        if not path.startswith("/api/"):
            return self._static(path)
        if method in ("POST", "PUT", "DELETE"):
            self._origin_check()
        query = parse_qs(urlparse(self.path).query)
        if path == "/api/store" and method == "GET":
            return self._public_store()
        if path == "/api/categories" and method == "GET":
            return self._categories()
        if path == "/api/products" and method == "GET":
            return self._products(query)
        if path == "/api/areas" and method == "GET":
            return self._areas()
        if path == "/api/business-logo" and method == "GET":
            return self._business_logo()
        if path.startswith("/api/product-images/") and method == "GET":
            return self._product_image(path.removeprefix("/api/product-images/"))
        if path == "/api/cart":
            return self._cart_api(method)
        if path == "/api/orders" and method == "POST":
            return self._create_order()
        if path == "/api/admin/login" and method == "POST":
            return self._login()
        if path == "/api/admin/session" and method == "GET":
            return self._admin_session()
        if path == "/api/admin/logout" and method == "POST":
            self._logout()
            return
        if path.startswith("/api/admin/"):
            return self._admin_api(path, method, query)
        fail("المسار المطلوب غير موجود.", 404)

    def _static(self, path):
        if path in ("/admin", "/admin/"):
            path = "/admin.html"
        if path == "/":
            path = "/index.html"
        requested = (PUBLIC / path.lstrip("/")).resolve()
        if not requested.is_relative_to(PUBLIC.resolve()) or not requested.is_file():
            fail("الصفحة المطلوبة غير موجودة.", 404)
        mime = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".webp": "image/webp",
        }.get(requested.suffix, "application/octet-stream")
        self._send(200, requested.read_bytes(), mime)

    def _public_receipt(self, path):
        token = path.removeprefix("/receipt/").removesuffix(".pdf")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            fail("الإيصال غير موجود.", 404)
        with database.connect() as db:
            receipt = db.execute(
                "SELECT receipt_number,pdf_data FROM receipts WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
        if not receipt:
            fail("الإيصال غير موجود.", 404)
        return self._send(200, receipt["pdf_data"], "application/pdf", {
            "Content-Disposition": f'attachment; filename="receipt-{receipt["receipt_number"]}.pdf"',
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        })

    def _business_logo(self):
        with database.connect() as db:
            asset = db.execute(
                "SELECT content,mime_type FROM business_assets WHERE asset_key='logo'"
            ).fetchone()
        if not asset:
            fail("شعار المتجر غير موجود.", 404)
        return self._send(200, asset["content"], asset["mime_type"], {
            "Cache-Control": "no-cache",
        })

    def _product_image(self, image_id_value):
        image_id = safe_int(image_id_value, "الصورة", 1)
        with database.connect() as db:
            image = db.execute(
                "SELECT i.image_data,i.image_mime_type FROM product_images i "
                "JOIN products p ON p.id=i.product_id "
                "JOIN product_categories c ON c.id=p.category_id "
                "WHERE i.id=? AND p.available=1 AND c.active=1",
                (image_id,),
            ).fetchone()
        if not image or not image["image_data"]:
            fail("الصورة غير موجودة.", 404)
        return self._send(200, image["image_data"], image["image_mime_type"], {
            "Cache-Control": "public, max-age=86400",
        })

    def _public_store(self):
        with database.connect() as db:
            settings = {
                row["key"]: row["value"]
                for row in db.execute(
                    "SELECT key,value FROM business_settings WHERE key IN "
                    "('business_name','business_name_ar','phone','address','instagram_url','facebook_url',"
                    "'payment_cash_enabled','delivery_enabled','store_enabled')"
                )
            }
            hours = [row_dict(r) for r in db.execute(
                "SELECT weekday,opens_at,closes_at,active FROM working_hours ORDER BY weekday"
            )]
            banners = [row_dict(r) for r in db.execute(
                "SELECT id,title_ar,description_ar,image_url FROM promotional_banners "
                "WHERE active=1 ORDER BY sort_order,id"
            )]
            is_open = store_status(db)
        return self._json(200, {
            "settings": settings, "hours": hours, "isOpen": is_open,
            "storeStatus": "مفتوح الآن" if is_open else "مغلق الآن",
            "banners": banners,
        })

    def _categories(self):
        with database.connect() as db:
            categories = [row_dict(r) for r in db.execute(
                "SELECT c.id,c.name_ar,c.slug,c.sort_order,COUNT(p.id) AS product_count "
                "FROM product_categories c LEFT JOIN products p ON p.category_id=c.id AND p.available=1 "
                "WHERE c.active=1 GROUP BY c.id ORDER BY c.sort_order,c.name_ar"
            )]
        return self._json(200, categories)

    def _products(self, query):
        category = query.get("category", [""])[0]
        search = query.get("q", [""])[0].strip()[:100]
        group = query.get("group", [""])[0]
        with database.connect() as db:
            clauses = ["p.available=1", "c.active=1"]
            params = []
            if group == "featured":
                clauses.append("p.featured=1")
            elif group == "new":
                clauses.append("p.is_new=1")
            elif group == "bestsellers":
                clauses.append(
                    "EXISTS (SELECT 1 FROM order_items oi JOIN orders o ON o.id=oi.order_id "
                    "WHERE oi.product_id=p.id AND o.status!='cancelled')"
                )
            elif group:
                fail("مجموعة المنتجات غير معروفة.")
            if category.isdigit():
                clauses.append("p.category_id=?")
                params.append(int(category))
            if search:
                clauses.append("(p.name_ar LIKE ? OR p.description_ar LIKE ?)")
                params.extend((f"%{search}%", f"%{search}%"))
            rows = db.execute(
                "SELECT p.*,c.name_ar AS category_name,"
                "COALESCE((SELECT SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id "
                "WHERE oi.product_id=p.id AND o.status!='cancelled'),0) AS units_sold FROM products p "
                "JOIN product_categories c ON c.id=p.category_id WHERE "
                + " AND ".join(clauses)
                + (" ORDER BY units_sold DESC,p.id" if group == "bestsellers"
                   else " ORDER BY p.featured DESC,p.sort_order,p.id"),
                params,
            ).fetchall()
            products = []
            for row in rows:
                product = row_dict(row)
                product["images"] = [
                    r["image_url"] for r in db.execute(
                        "SELECT image_url FROM product_images WHERE product_id=? ORDER BY sort_order,id",
                        (row["id"],),
                    )
                ]
                product["variants"] = [row_dict(r) for r in db.execute(
                    "SELECT id,name_ar,price_iqd,available FROM product_variants "
                    "WHERE product_id=? AND available=1 ORDER BY id", (row["id"],)
                )]
                products.append(product)
        return self._json(200, products)

    def _areas(self):
        with database.connect() as db:
            rows = [row_dict(r) for r in db.execute(
                "SELECT id,name_ar,district,fee_iqd FROM delivery_areas "
                "WHERE active=1 ORDER BY district,name_ar"
            )]
        return self._json(200, rows)

    def _cart_api(self, method):
        set_cookie = None
        with database.connect() as db:
            cart_id, set_cookie = self._cart(db, create=(method in ("GET", "PUT")))
            if method == "GET":
                items = []
                if cart_id:
                    rows = db.execute(
                        "SELECT ci.product_id,ci.variant_id,ci.quantity,p.name_ar,p.price_iqd,"
                        "v.name_ar AS variant_name,v.price_iqd AS variant_price "
                        "FROM cart_items ci JOIN products p ON p.id=ci.product_id "
                        "LEFT JOIN product_variants v ON v.id=ci.variant_id "
                        "WHERE ci.cart_id=? ORDER BY p.id", (cart_id,)
                    ).fetchall()
                    for row in rows:
                        price = row["variant_price"] if row["variant_id"] else row["price_iqd"]
                        items.append({
                            "productId": row["product_id"], "variantId": row["variant_id"],
                            "quantity": row["quantity"], "name": row["name_ar"],
                            "variantName": row["variant_name"] or "", "price": price,
                            "lineTotal": price * row["quantity"] if price else None,
                        })
                return self._json(200, {"items": items}, {"Set-Cookie": set_cookie} if set_cookie else None)
            if method != "PUT":
                fail("الطريقة غير مدعومة.", 405)
            data = self._body()
            items = data.get("items")
            if not isinstance(items, list) or len(items) > 100:
                fail("محتويات السلة غير صحيحة.")
            if cart_id is None:
                cart_id, set_cookie = self._cart(db)
            db.execute("DELETE FROM cart_items WHERE cart_id=?", (cart_id,))
            merged = {}
            for item in items:
                if not isinstance(item, dict):
                    fail("أحد عناصر السلة غير صحيح.")
                product_id = safe_int(item.get("productId"), "المنتج", 1)
                variant = item.get("variantId")
                variant_id = safe_int(variant, "الخيار", 1) if variant is not None else None
                quantity = safe_int(item.get("quantity"), "الكمية", 1, 99)
                key = (product_id, variant_id)
                merged[key] = merged.get(key, 0) + quantity
                if merged[key] > 99:
                    fail("الكمية القصوى للمنتج هي 99.")
                valid = db.execute(
                    "SELECT p.id FROM products p JOIN product_categories c ON c.id=p.category_id "
                    "WHERE p.id=? AND p.available=1 AND c.active=1",
                    (product_id,),
                ).fetchone()
                if not valid:
                    fail("أحد المنتجات لم يعد متاحاً.")
                if variant_id is not None and not db.execute(
                    "SELECT id FROM product_variants WHERE id=? AND product_id=? AND available=1",
                    (variant_id, product_id),
                ).fetchone():
                    fail("أحد خيارات المنتج لم يعد متاحاً.")
            db.executemany(
                "INSERT INTO cart_items (cart_id,product_id,variant_id,quantity) VALUES (?,?,?,?)",
                ((cart_id, product_id, variant_id, quantity)
                 for (product_id, variant_id), quantity in merged.items()),
            )
            db.execute("UPDATE carts SET updated_at=? WHERE id=?", (database.utc_now(), cart_id))
        return self._json(200, {"ok": True}, {"Set-Cookie": set_cookie} if set_cookie else None)

    def _create_order(self):
        data = self._body()
        name = require_text(data, "fullName", "الاسم الكامل", 120)
        phone = normalize_phone(data.get("phone"))
        if not PHONE_RE.fullmatch(phone):
            fail("يرجى إدخال رقم هاتف صحيح.")
        address = require_text(data, "address", "عنوان التوصيل", 500)
        instructions = str(data.get("instructions", "")).strip()
        if len(instructions) > 500:
            fail("الملاحظات يجب ألا تتجاوز 500 حرف.")
        payment_method = data.get("paymentMethod", "cash_on_delivery")
        with database.connect() as db:
            if not store_status(db):
                fail("المتجر مغلق الآن، ولا يمكن تأكيد الطلب خارج أوقات العمل.", 409)
            if get_setting(db, "delivery_enabled", "1") != "1":
                fail("التوصيل غير متاح حالياً.", 409)
            if payment_method == "electronic":
                if get_setting(db, "payment_electronic_enabled") != "1":
                    fail("الدفع الإلكتروني غير متاح حالياً. اختر الدفع النقدي عند الاستلام.", 409)
                fail("لم يتم ربط مزود دفع إلكتروني موثّق بعد؛ لم يتم إنشاء أي عملية دفع.", 503)
            if payment_method != "cash_on_delivery":
                fail("طريقة الدفع المحددة غير مدعومة.", 400)
            if get_setting(db, "payment_cash_enabled", "1") != "1":
                fail("الدفع عند الاستلام غير متاح حالياً.", 409)
            area_id = safe_int(data.get("areaId"), "منطقة التوصيل", 1)
            area = db.execute(
                "SELECT id,name_ar,district,fee_iqd FROM delivery_areas WHERE id=? AND active=1",
                (area_id,),
            ).fetchone()
            if not area:
                fail("منطقة التوصيل غير متاحة حالياً.", 409)
            cart_id, _ = self._cart(db, create=False)
            if not cart_id:
                fail("سلة التسوق فارغة.", 409)
            rows = db.execute(
                "SELECT ci.product_id,ci.variant_id,ci.quantity,p.name_ar,p.price_iqd,p.available,"
                "c.active AS category_active,v.name_ar AS variant_name,v.price_iqd AS variant_price,v.available AS variant_available "
                "FROM cart_items ci JOIN products p ON p.id=ci.product_id "
                "JOIN product_categories c ON c.id=p.category_id "
                "LEFT JOIN product_variants v ON v.id=ci.variant_id WHERE ci.cart_id=?",
                (cart_id,),
            ).fetchall()
            if not rows:
                fail("سلة التسوق فارغة.", 409)
            subtotal = 0
            order_items = []
            for row in rows:
                if not row["available"] or not row["category_active"]:
                    fail(f"المنتج «{row['name_ar']}» لم يعد متاحاً.")
                if row["variant_id"]:
                    if not row["variant_available"] or row["variant_price"] is None:
                        fail(f"خيار المنتج «{row['name_ar']}» لم يعد متاحاً.")
                    price = row["variant_price"]
                else:
                    if row["price_iqd"] is None:
                        fail(f"لم يُحدد سعر المنتج «{row['name_ar']}» بعد.")
                    price = row["price_iqd"]
                line_total = price * row["quantity"]
                subtotal += line_total
                order_items.append((row, price, line_total))
            now = database.utc_now()
            db.execute(
                "INSERT INTO customers (full_name,phone,created_at,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(phone) DO UPDATE SET full_name=excluded.full_name,updated_at=excluded.updated_at",
                (name, phone, now, now),
            )
            customer_id = db.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()["id"]
            order_number = "VN-" + datetime.now(TIMEZONE).strftime("%y%m%d") + "-" + secrets.token_hex(3).upper()
            cursor = db.execute(
                "INSERT INTO orders (order_number,customer_id,delivery_area_id,delivery_area_name,"
                "delivery_district,delivery_address,delivery_instructions,delivery_fee_iqd,"
                "delivery_fee_determined,subtotal_iqd,total_iqd,status,payment_method,payment_status,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'new','cash_on_delivery','pending',?,?)",
                (order_number, customer_id, area["id"], area["name_ar"], area["district"],
                 address, instructions, area["fee_iqd"] or 0, int(area["fee_iqd"] is not None),
                 subtotal, subtotal + (area["fee_iqd"] or 0), now, now),
            )
            order_id = cursor.lastrowid
            db.executemany(
                "INSERT INTO order_items (order_id,product_id,product_name_ar,variant_name_ar,"
                "quantity,unit_price_iqd,line_total_iqd) VALUES (?,?,?,?,?,?,?)",
                ((order_id, item["product_id"], item["name_ar"], item["variant_name"] or "",
                  item["quantity"], price, line_total) for item, price, line_total in order_items),
            )
            if area["fee_iqd"] is not None:
                db.execute(
                    "INSERT INTO payment_transactions (order_id,provider,amount_iqd,status,created_at,updated_at) "
                    "VALUES (?,'cash_on_delivery',?,'pending',?,?)",
                    (order_id, subtotal + area["fee_iqd"], now, now),
                )
            db.execute(
                "INSERT INTO order_status_history (order_id,status,created_at) VALUES (?,'new',?)",
                (order_id, now),
            )
            db.execute(
                "INSERT INTO notifications (order_id,channel,message,status,created_at) VALUES "
                "(?,'admin','طلب جديد ' || ?,'pending',?)",
                (order_id, order_number, now),
            )
            db.execute("DELETE FROM cart_items WHERE cart_id=?", (cart_id,))
            receipt_number, receipt_token, _ = self._build_order_receipt(db, order_id)
        return self._json(201, {
            "orderNumber": order_number, "status": "new",
            "subtotal": subtotal, "deliveryFee": area["fee_iqd"],
            "total": subtotal + area["fee_iqd"] if area["fee_iqd"] is not None else None,
            "deliveryFeeDetermined": area["fee_iqd"] is not None,
            "paymentStatus": "pending",
            "receiptNumber": receipt_number,
            "receiptUrl": f"/receipt/{receipt_token}.pdf",
        })

    def _login(self):
        self._origin_check()
        data = self._body()
        username = require_text(data, "username", "اسم المستخدم", 80)
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 1024:
            fail("بيانات الدخول غير صحيحة.", 401)
        now = time.time()
        address = self.client_address[0]
        attempts, blocked_until = LOGIN_ATTEMPTS.get(address, (0, 0))
        if blocked_until > now:
            fail("محاولات كثيرة. يرجى الانتظار قليلاً ثم المحاولة.", 429)
        with database.connect() as db:
            user = db.execute(
                "SELECT id,password_hash,role,active FROM staff_users WHERE username=?",
                (username,),
            ).fetchone()
            valid = False
            if user:
                try:
                    salt = bytes.fromhex(user["password_hash"][:32])
                    expected = hashlib.scrypt(
                        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
                    ).hex()
                    valid = hmac.compare_digest(expected, user["password_hash"][32:]) and bool(user["active"])
                except (ValueError, TypeError):
                    valid = False
            if not valid:
                attempts += 1
                LOGIN_ATTEMPTS[address] = (attempts, now + 300 if attempts >= 5 else 0)
                fail("اسم المستخدم أو كلمة المرور غير صحيحة.", 401)
            LOGIN_ATTEMPTS.pop(address, None)
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            created = datetime.now(timezone.utc)
            db.execute(
                "INSERT INTO admin_sessions (token_hash,staff_user_id,csrf_token,expires_at,created_at) "
                "VALUES (?,?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf,
                 (created + timedelta(hours=12)).isoformat(timespec="seconds"),
                 created.isoformat(timespec="seconds")),
            )
        headers = {"Set-Cookie": self._set_cookie(
            "venito_admin", token, 60 * 60 * 12, same_site="Strict"
        )}
        return self._json(200, {
            "user": {"username": username, "role": user["role"]},
            "csrfToken": csrf,
        }, headers)

    def _admin_session(self):
        user = self._admin()
        with database.connect() as db:
            session = db.execute(
                "SELECT csrf_token FROM admin_sessions WHERE token_hash=?",
                (hashlib.sha256(self._cookie("venito_admin").encode()).hexdigest(),),
            ).fetchone()
        return self._json(200, {
            "user": {"username": user["username"], "role": user["role"]},
            "csrfToken": session["csrf_token"],
        })

    def _logout(self):
        user = self._admin(mutation=True)
        del user
        token = self._cookie("venito_admin")
        with database.connect() as db:
            db.execute(
                "DELETE FROM admin_sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )
        self._json(200, {"ok": True}, {
            "Set-Cookie": self._set_cookie("venito_admin", "", 0, same_site="Strict")
        })

    def _admin_api(self, path, method, query):
        user = self._admin(mutation=method in ("POST", "PUT", "DELETE"))
        if method in ("POST", "PUT", "DELETE") and user["role"] not in ("admin", "manager"):
            fail("ليست لديك صلاحية تعديل البيانات.", 403)
        segments = path.removeprefix("/api/admin/").strip("/").split("/")
        resource = segments[0]
        if resource == "summary" and method == "GET":
            return self._admin_summary()
        if resource == "products":
            return self._admin_products(method, segments[1:] if len(segments) > 1 else [])
        if resource == "categories":
            return self._admin_categories(method, segments[1:] if len(segments) > 1 else [])
        if resource == "areas":
            return self._admin_areas(method, segments[1:] if len(segments) > 1 else [])
        if resource == "orders":
            if len(segments) == 3 and segments[2] == "receipt" and method == "GET":
                return self._admin_receipt(segments[1])
            if len(segments) == 3 and segments[2] == "print" and method == "POST":
                return self._print_order(segments[1], self._body())
            return self._admin_orders(method, segments[1:] if len(segments) > 1 else [], query, user["id"])
        if resource == "customers" and method == "GET":
            return self._admin_customers(query)
        if resource == "printer-test" and method == "POST":
            self._body()
            return self._printer_test()
        if resource == "settings":
            return self._admin_settings(method)
        if resource == "logo":
            return self._admin_logo(method)
        if resource == "reports" and method == "GET":
            return self._admin_reports(query)
        if resource == "banners":
            return self._admin_banners(method, segments[1:] if len(segments) > 1 else [])
        if resource == "staff":
            return self._admin_staff(method, segments[1:] if len(segments) > 1 else [], user)
        fail("المسار الإداري غير موجود.", 404)

    def _build_order_receipt(self, db, order_id):
        order = db.execute(
            "SELECT o.*,c.full_name,c.phone FROM orders o "
            "JOIN customers c ON c.id=o.customer_id WHERE o.id=?",
            (order_id,),
        ).fetchone()
        if not order:
            fail("الطلب غير موجود.", 404)
        items = db.execute(
            "SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order_id,)
        ).fetchall()
        logo = db.execute(
            "SELECT content FROM business_assets WHERE asset_key='logo'"
        ).fetchone()
        receipt_number = (
            "VR-" + datetime.now(TIMEZONE).strftime("%y%m%d") + "-"
            + secrets.token_hex(8).upper()
        )
        token = secrets.token_urlsafe(32)
        pdf_data = build_receipt_pdf(
            order,
            items,
            receipt_number,
            get_setting(db, "business_name_ar", "حلويات ومعجنات فينتو"),
            get_setting(db, "phone"),
            get_setting(db, "address"),
            get_setting(db, "receipt_footer"),
            logo["content"] if logo else None,
        )
        db.execute(
            "INSERT INTO receipts (order_id,receipt_number,token_hash,pdf_data,created_at) "
            "VALUES (?,?,?,?,?)",
            (
                order_id, receipt_number, hashlib.sha256(token.encode()).hexdigest(),
                pdf_data, database.utc_now(),
            ),
        )
        return receipt_number, token, pdf_data

    def _admin_receipt(self, order_id_value):
        order_id = safe_int(order_id_value, "الطلب", 1)
        with database.connect() as db:
            receipt = db.execute(
                "SELECT receipt_number,pdf_data FROM receipts WHERE order_id=?",
                (order_id,),
            ).fetchone()
            if not receipt:
                receipt_number, _, pdf_data = self._build_order_receipt(db, order_id)
            else:
                receipt_number, pdf_data = receipt["receipt_number"], receipt["pdf_data"]
        return self._send(200, pdf_data, "application/pdf", {
            "Content-Disposition": f'inline; filename="receipt-{receipt_number}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex, nofollow",
        })

    def _admin_logo(self, method):
        with database.connect() as db:
            if method == "PUT":
                content, mime_type = decode_image_data(self._body().get("imageData"))
                db.execute(
                    "INSERT INTO business_assets (asset_key,content,mime_type,updated_at) "
                    "VALUES ('logo',?,?,?) ON CONFLICT(asset_key) DO UPDATE SET "
                    "content=excluded.content,mime_type=excluded.mime_type,updated_at=excluded.updated_at",
                    (content, mime_type, database.utc_now()),
                )
                db.commit()
                return self._json(200, {"ok": True})
            if method == "DELETE":
                db.execute("DELETE FROM business_assets WHERE asset_key='logo'")
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _admin_summary(self):
        with database.connect() as db:
            local_today = datetime.now(TIMEZONE).date()
            today = local_today.isoformat()
            month_start = local_today.replace(day=1).isoformat()
            counts = {row["status"]: row["count"] for row in db.execute(
                "SELECT status,COUNT(*) AS count FROM orders GROUP BY status"
            )}
            sales_expression = "CASE WHEN status!='cancelled' THEN subtotal_iqd ELSE 0 END"
            daily_sales = db.execute(
                f"SELECT COALESCE(SUM({sales_expression}),0) FROM orders "
                "WHERE date(created_at,'+3 hours')=?",
                (today,),
            ).fetchone()[0]
            monthly_sales = db.execute(
                f"SELECT COALESCE(SUM({sales_expression}),0) FROM orders "
                "WHERE date(created_at,'+3 hours')>=? AND date(created_at,'+3 hours')<=?",
                (month_start, today),
            ).fetchone()[0]
            chart_start = (local_today - timedelta(days=13)).isoformat()
            chart_values = {
                row["day"]: row["sales"] for row in db.execute(
                    f"SELECT date(created_at,'+3 hours') AS day,SUM({sales_expression}) AS sales "
                    "FROM orders WHERE date(created_at,'+3 hours')>=? "
                    "AND date(created_at,'+3 hours')<=? GROUP BY day",
                    (chart_start, today),
                )
            }
            sales_chart = [
                {"day": (local_today - timedelta(days=offset)).isoformat(),
                 "sales": chart_values.get((local_today - timedelta(days=offset)).isoformat(), 0)}
                for offset in range(13, -1, -1)
            ]
            recent = [order_dict(r) for r in db.execute(
                "SELECT o.order_number,o.status,o.total_iqd,o.delivery_fee_determined,o.created_at,c.full_name "
                " ,o.id "
                "FROM orders o JOIN customers c ON c.id=o.customer_id "
                "ORDER BY o.id DESC LIMIT 8"
            )]
            products = db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
            total_orders = sum(counts.values())
            today_orders = db.execute(
                "SELECT COUNT(*) FROM orders WHERE date(created_at,'+3 hours')=?",
                (today,),
            ).fetchone()[0]
        pending = counts.get("new", 0) + counts.get("confirmed", 0)
        return self._json(200, {
            "todayOrders": today_orders,
            "todaySales": daily_sales,
            "monthlySales": monthly_sales,
            "totalOrders": total_orders,
            "newOrders": counts.get("new", 0),
            "pendingOrders": pending,
            "preparingOrders": counts.get("preparing", 0),
            "completedOrders": counts.get("delivered", 0),
            "cancelledOrders": counts.get("cancelled", 0),
            "products": products,
            "statuses": counts,
            "salesChart": sales_chart,
            "recentOrders": recent,
        })

    def _admin_products(self, method, ids):
        with database.connect() as db:
            if method == "GET":
                rows = db.execute(
                    "SELECT p.*,c.name_ar AS category_name FROM products p "
                    "JOIN product_categories c ON c.id=p.category_id ORDER BY p.id DESC"
                ).fetchall()
                result = []
                for row in rows:
                    item = row_dict(row)
                    item["images"] = [r["image_url"] for r in db.execute(
                        "SELECT image_url FROM product_images WHERE product_id=? ORDER BY sort_order,id",
                        (row["id"],),
                    )]
                    item["variants"] = [row_dict(r) for r in db.execute(
                        "SELECT id,name_ar,price_iqd,available FROM product_variants WHERE product_id=? ORDER BY id",
                        (row["id"],),
                    )]
                    result.append(item)
                return self._json(200, result)
            if method == "POST":
                data = self._body()
                product_id = self._save_product(db, data)
                db.commit()
                return self._json(201, {"id": product_id})
            if len(ids) != 1 or not ids[0].isdigit():
                fail("رقم المنتج غير صحيح.", 400)
            product_id = int(ids[0])
            if method == "DELETE":
                if not db.execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone():
                    fail("المنتج غير موجود.", 404)
                db.execute("UPDATE products SET available=0,updated_at=? WHERE id=?",
                           (database.utc_now(), product_id))
                db.commit()
                return self._json(200, {"ok": True})
            if method == "PUT":
                data = self._body()
                self._save_product(db, data, product_id)
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _save_product(self, db, data, product_id=None):
        name = require_text(data, "name", "اسم المنتج", 160)
        description = str(data.get("description", "")).strip()
        if len(description) > 2000:
            fail("وصف المنتج طويل جداً.")
        category_id = safe_int(data.get("categoryId"), "التصنيف", 1)
        if not db.execute(
            "SELECT id FROM product_categories WHERE id=? AND active=1", (category_id,)
        ).fetchone():
            fail("التصنيف غير متاح.")
        price = data.get("price")
        price = None if price in ("", None) else safe_int(price, "السعر", 1)
        image_urls = data.get("images", [])
        if not isinstance(image_urls, list) or len(image_urls) > 8:
            fail("صور المنتج غير صحيحة.")
        for url in image_urls:
            if not isinstance(url, str) or len(url) > 1000 or not (
            (url.startswith("/") and not url.startswith("//")) or url.startswith("https://")
            ):
                fail("رابط إحدى الصور غير آمن أو غير صحيح.")
        image_data = None
        if data.get("imageData"):
            image_data = decode_image_data(data["imageData"])
        variants = data.get("variants", [])
        if not isinstance(variants, list) or len(variants) > 30:
            fail("خيارات المنتج غير صحيحة.")
        prepared_variants = []
        for variant in variants:
            if not isinstance(variant, dict):
                fail("أحد خيارات المنتج غير صحيح.")
            variant_name = require_text(variant, "name", "اسم الخيار", 100)
            variant_price = variant.get("price")
            variant_price = None if variant_price in ("", None) else safe_int(variant_price, "السعر", 1)
            prepared_variants.append((variant_name, variant_price, bool_value(variant.get("available", True))))
        now = database.utc_now()
        fields = (
            category_id, name, description, price, bool_value(data.get("available", True)),
            bool_value(data.get("featured")), bool_value(data.get("isNew")),
            safe_int(data.get("sortOrder", 0), "الترتيب", 0, 100000), now,
        )
        if product_id:
            exists = db.execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone()
            if not exists:
                fail("المنتج غير موجود.", 404)
            db.execute(
                "UPDATE products SET category_id=?,name_ar=?,description_ar=?,price_iqd=?,available=?,"
                "featured=?,is_new=?,sort_order=?,updated_at=? WHERE id=?",
                (*fields, product_id),
            )
        else:
            cursor = db.execute(
                "INSERT INTO products (category_id,name_ar,description_ar,price_iqd,available,featured,"
                "is_new,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (*fields[:-1], now, now),
            )
            product_id = cursor.lastrowid
        if "images" in data or image_data:
            db.execute("DELETE FROM product_images WHERE product_id=?", (product_id,))
            db.executemany(
                "INSERT INTO product_images (product_id,image_url,alt_ar,sort_order) VALUES (?,?,?,?)",
                ((product_id, url, name, index) for index, url in enumerate(image_urls)),
            )
            if image_data:
                content, mime_type = image_data
                cursor = db.execute(
                    "INSERT INTO product_images "
                    "(product_id,image_url,alt_ar,sort_order,image_data,image_mime_type) "
                    "VALUES (?,'',?,?,?,?)",
                    (product_id, name, len(image_urls), content, mime_type),
                )
                db.execute(
                    "UPDATE product_images SET image_url=? WHERE id=?",
                    (f"/api/product-images/{cursor.lastrowid}", cursor.lastrowid),
                )
        db.execute("DELETE FROM product_variants WHERE product_id=?", (product_id,))
        db.executemany(
            "INSERT INTO product_variants (product_id,name_ar,price_iqd,available) VALUES (?,?,?,?)",
            ((product_id, *variant) for variant in prepared_variants),
        )
        return product_id

    def _admin_categories(self, method, ids):
        with database.connect() as db:
            if method == "GET":
                return self._json(200, [row_dict(r) for r in db.execute(
                    "SELECT * FROM product_categories ORDER BY sort_order,id"
                )])
            if method == "POST":
                data = self._body()
                name = require_text(data, "name", "اسم التصنيف", 100)
                slug = require_text(data, "slug", "معرّف التصنيف", 100)
                if not re.fullmatch(r"[a-z0-9-]+", slug):
                    fail("معرّف التصنيف يقبل الأحرف الإنجليزية الصغيرة والأرقام والشرطة فقط.")
                try:
                    cursor = db.execute(
                        "INSERT INTO product_categories (name_ar,slug,sort_order,active,created_at) "
                        "VALUES (?,?,?,?,?)",
                        (name, slug, safe_int(data.get("sortOrder", 0), "الترتيب", 0, 100000),
                         bool_value(data.get("active", True)), database.utc_now()),
                    )
                except sqlite3.IntegrityError:
                    fail("معرّف التصنيف مستخدم مسبقاً.")
                db.commit()
                return self._json(201, {"id": cursor.lastrowid})
            if len(ids) != 1 or not ids[0].isdigit():
                fail("رقم التصنيف غير صحيح.")
            category_id = int(ids[0])
            data = self._body() if method == "PUT" else {}
            if method in ("PUT", "DELETE"):
                current = db.execute(
                    "SELECT * FROM product_categories WHERE id=?", (category_id,)
                ).fetchone()
                if not current:
                    fail("التصنيف غير موجود.", 404)
                if method == "DELETE":
                    db.execute("UPDATE product_categories SET active=0 WHERE id=?", (category_id,))
                else:
                    name = require_text(data, "name", "اسم التصنيف", 100)
                    slug = require_text(data, "slug", "معرّف التصنيف", 100)
                    if not re.fullmatch(r"[a-z0-9-]+", slug):
                        fail("معرّف التصنيف غير صحيح.")
                    db.execute(
                        "UPDATE product_categories SET name_ar=?,slug=?,sort_order=?,active=? WHERE id=?",
                        (name, slug, safe_int(data.get("sortOrder", 0), "الترتيب", 0, 100000),
                         bool_value(data.get("active", True)), category_id),
                    )
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _admin_areas(self, method, ids):
        with database.connect() as db:
            if method == "GET":
                return self._json(200, [row_dict(r) for r in db.execute(
                    "SELECT * FROM delivery_areas ORDER BY district,name_ar"
                )])
            if method == "POST":
                data = self._body()
                name = require_text(data, "name", "اسم المنطقة", 120)
                district = data.get("district")
                if district not in DISTRICTS:
                    fail("يرجى اختيار جانب بغداد الصحيح.")
                fee = data.get("fee")
                fee = None if fee in ("", None) else safe_int(fee, "أجرة التوصيل", 0)
                cursor = db.execute(
                    "INSERT INTO delivery_areas (name_ar,district,fee_iqd,active,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (name, district, fee, bool_value(data.get("active", True)), database.utc_now()),
                )
                db.commit()
                return self._json(201, {"id": cursor.lastrowid})
            if len(ids) != 1 or not ids[0].isdigit():
                fail("رقم المنطقة غير صحيح.")
            area_id = int(ids[0])
            if method == "DELETE":
                db.execute("UPDATE delivery_areas SET active=0 WHERE id=?", (area_id,))
                db.commit()
                return self._json(200, {"ok": True})
            if method == "PUT":
                data = self._body()
                name = require_text(data, "name", "اسم المنطقة", 120)
                district = data.get("district")
                if district not in DISTRICTS:
                    fail("يرجى اختيار جانب بغداد الصحيح.")
                fee = data.get("fee")
                fee = None if fee in ("", None) else safe_int(fee, "أجرة التوصيل", 0)
                cursor = db.execute(
                    "UPDATE delivery_areas SET name_ar=?,district=?,fee_iqd=?,active=? WHERE id=?",
                    (name, district, fee, bool_value(data.get("active", True)), area_id),
                )
                if not cursor.rowcount:
                    fail("المنطقة غير موجودة.", 404)
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _admin_orders(self, method, ids, query, staff_id):
        with database.connect() as db:
            if not ids and method == "GET":
                clauses, params = [], []
                status = query.get("status", [""])[0]
                search = query.get("q", [""])[0].strip()[:100]
                if status and status not in STATUSES and status != "pending":
                    fail("حالة الطلب غير معروفة.")
                if status == "pending":
                    clauses.append("o.status IN ('new','confirmed')")
                elif status:
                    clauses.append("o.status=?")
                    params.append(status)
                if search:
                    clauses.append("(o.order_number LIKE ? OR c.full_name LIKE ? OR c.phone LIKE ?)")
                    params.extend((f"%{search}%", f"%{search}%", f"%{search}%"))
                date_from = query.get("dateFrom", [""])[0]
                date_to = query.get("dateTo", [""])[0]
                parsed_dates = {}
                for key, value in (("dateFrom", date_from), ("dateTo", date_to)):
                    if value:
                        try:
                            parsed_dates[key] = datetime.strptime(value, "%Y-%m-%d").date()
                        except ValueError:
                            fail("صيغة تاريخ الطلب غير صحيحة.")
                        if parsed_dates[key].isoformat() != value:
                            fail("صيغة تاريخ الطلب غير صحيحة.")
                if date_from and date_to and parsed_dates["dateFrom"] > parsed_dates["dateTo"]:
                    fail("تاريخ البداية يجب ألا يتجاوز تاريخ النهاية.")
                if date_from:
                    clauses.append("date(o.created_at,'+3 hours')>=?")
                    params.append(date_from)
                if date_to:
                    clauses.append("date(o.created_at,'+3 hours')<=?")
                    params.append(date_to)
                area_id = query.get("areaId", [""])[0]
                if area_id:
                    clauses.append("o.delivery_area_id=?")
                    params.append(safe_int(area_id, "منطقة التوصيل", 1))
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                rows = db.execute(
                    "SELECT o.*,c.full_name,c.phone FROM orders o JOIN customers c ON c.id=o.customer_id"
                    + where + " ORDER BY o.id DESC LIMIT 300", params
                ).fetchall()
                return self._json(200, [order_dict(r) for r in rows])
            if len(ids) < 1:
                fail("رقم الطلب مطلوب.", 400)
            if ids[0] == "print" and len(ids) == 2 and method == "POST":
                return self._print_order(ids[1], self._body())
            if not ids[0].isdigit():
                fail("رقم الطلب غير صحيح.", 400)
            order_id = int(ids[0])
            if len(ids) == 1 and method == "GET":
                order = db.execute(
                    "SELECT o.*,c.full_name,c.phone FROM orders o JOIN customers c ON c.id=o.customer_id "
                    "WHERE o.id=?", (order_id,)
                ).fetchone()
                if not order:
                    fail("الطلب غير موجود.", 404)
                result = order_dict(order)
                result["items"] = [row_dict(r) for r in db.execute(
                    "SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order_id,)
                )]
                result["history"] = [row_dict(r) for r in db.execute(
                    "SELECT status,created_at FROM order_status_history WHERE order_id=? ORDER BY id",
                    (order_id,),
                )]
                receipt = db.execute(
                    "SELECT receipt_number FROM receipts WHERE order_id=?", (order_id,)
                ).fetchone()
                result["receipt_number"] = receipt["receipt_number"] if receipt else None
                return self._json(200, result)
            if len(ids) == 1 and method == "PUT":
                data = self._body()
                status = data.get("status")
                if status not in STATUSES:
                    fail("حالة الطلب غير معروفة.")
                order = db.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
                if not order:
                    fail("الطلب غير موجود.", 404)
                if order["status"] in ("delivered", "cancelled") and status != order["status"]:
                    fail("لا يمكن تغيير حالة طلب مكتمل أو ملغي.", 409)
                now = database.utc_now()
                db.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?", (status, now, order_id))
                db.execute(
                    "INSERT INTO order_status_history (order_id,status,changed_by,created_at) VALUES (?,?,?,?)",
                    (order_id, status, staff_id, now),
                )
                db.execute(
                    "INSERT INTO notifications (order_id,channel,message,status,created_at) VALUES "
                    "(?,'customer',?,'pending',?)",
                    (order_id, f"تم تحديث حالة طلبك إلى: {STATUSES[status]}", now),
                )
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _admin_customers(self, query):
        search = query.get("q", [""])[0].strip()[:100]
        with database.connect() as db:
            params = []
            where = ""
            if search:
                where = "WHERE c.full_name LIKE ? OR c.phone LIKE ?"
                params = [f"%{search}%", f"%{search}%"]
            rows = db.execute(
                "SELECT c.id,c.full_name,c.phone,c.created_at,COUNT(o.id) AS order_count,"
                "COALESCE(SUM(CASE WHEN o.status!='cancelled' THEN "
                "CASE WHEN o.delivery_fee_determined=1 THEN o.total_iqd ELSE o.subtotal_iqd END "
                "ELSE 0 END),0) AS total_spent "
                "FROM customers c LEFT JOIN orders o ON o.customer_id=c.id " + where
                + " GROUP BY c.id ORDER BY c.id DESC LIMIT 300", params
            )
            return self._json(200, [row_dict(r) for r in rows])

    def _admin_settings(self, method):
        with database.connect() as db:
            if method == "GET":
                settings = {r["key"]: r["value"] for r in db.execute(
                    "SELECT key,value FROM business_settings"
                )}
                hours = [row_dict(r) for r in db.execute(
                    "SELECT weekday,opens_at,closes_at,active FROM working_hours ORDER BY weekday"
                )]
                logo_available = bool(db.execute(
                    "SELECT 1 FROM business_assets WHERE asset_key='logo'"
                ).fetchone())
                return self._json(200, {
                    "settings": settings, "hours": hours, "logoAvailable": logo_available,
                })
            if method == "PUT":
                data = self._body()
                settings = data.get("settings", {})
                if not isinstance(settings, dict):
                    fail("إعدادات المتجر غير صحيحة.")
                allowed = {
                    "business_name", "business_name_ar", "phone", "address",
                    "instagram_url", "facebook_url", "payment_cash_enabled",
                    "payment_electronic_enabled", "printer_enabled", "printer_host",
                    "printer_port", "printer_paper_width", "store_enabled",
                    "delivery_enabled", "receipt_footer",
                }
                for key, value in settings.items():
                    if key not in allowed or not isinstance(value, (str, int, bool)):
                        fail("يتضمن الطلب إعداداً غير مسموح.")
                    value = str(int(value)) if isinstance(value, bool) else str(value).strip()
                    if len(value) > 500:
                        fail("إحدى قيم الإعدادات طويلة جداً.")
                    if key.endswith("_url") and value and not value.startswith("https://"):
                        fail("روابط التواصل يجب أن تبدأ بـ https://")
                    if key == "printer_port":
                        value = str(safe_int(value, "منفذ الطابعة", 1, 65535))
                    if key == "printer_paper_width" and value not in ("58", "80"):
                        fail("عرض الورق يجب أن يكون 58 أو 80 مم.")
                    if key == "printer_host" and any(char in value for char in "/\\@"):
                        fail("أدخل اسم مضيف أو عنوان IP فقط للطابعة.")
                    if key.startswith("payment_") or key in (
                        "printer_enabled", "store_enabled", "delivery_enabled",
                    ):
                        value = "1" if bool_value(value) else "0"
                    set_setting(db, key, value)
                hours = data.get("hours")
                if hours is not None:
                    if not isinstance(hours, list) or len(hours) != 7:
                        fail("يجب إدخال أوقات الأيام السبعة.")
                    seen = set()
                    for item in hours:
                        if not isinstance(item, dict):
                            fail("أحد جداول العمل غير صحيح.")
                        day = safe_int(item.get("weekday"), "اليوم", 0, 6)
                        if day in seen:
                            fail("اليوم مكرر في جدول العمل.")
                        seen.add(day)
                        opening = item.get("opensAt")
                        closing = item.get("closesAt")
                        if not all(isinstance(v, str) and re.fullmatch(r"\d{2}:\d{2}", v) for v in (opening, closing)):
                            fail("صيغة وقت العمل يجب أن تكون ساعة:دقيقة.")
                        if any(int(v[:2]) > 23 or int(v[3:]) > 59 for v in (opening, closing)):
                            fail("وقت العمل خارج النطاق.")
                        db.execute(
                            "UPDATE working_hours SET opens_at=?,closes_at=?,active=? WHERE weekday=?",
                            (opening, closing, bool_value(item.get("active")), day),
                        )
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _admin_reports(self, query):
        period = query.get("period", ["week"])[0]
        periods = {"day": 1, "week": 7, "month": 30}
        if period not in periods:
            fail("فترة التقرير غير معروفة.")
        local_now = datetime.now(TIMEZONE)
        date_from = query.get("dateFrom", [""])[0]
        date_to = query.get("dateTo", [""])[0]
        if bool(date_from) != bool(date_to):
            fail("أدخلوا تاريخ البداية والنهاية معاً.")
        if date_from:
            try:
                start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
                end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            except ValueError:
                fail("صيغة تاريخ التقرير غير صحيحة.")
            if start_date.isoformat() != date_from or end_date.isoformat() != date_to:
                fail("صيغة تاريخ التقرير غير صحيحة.")
            if start_date > end_date:
                fail("تاريخ البداية يجب ألا يتجاوز تاريخ النهاية.")
        else:
            end_date = local_now.date()
            start_date = end_date - timedelta(days=periods[period] - 1)
            date_from = start_date.isoformat()
            date_to = end_date.isoformat()
        local_start = datetime.combine(start_date, datetime.min.time(), tzinfo=TIMEZONE)
        local_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=TIMEZONE)
        since = local_start.astimezone(timezone.utc).isoformat(timespec="seconds")
        until = local_end.astimezone(timezone.utc).isoformat(timespec="seconds")
        with database.connect() as db:
            daily = [row_dict(r) for r in db.execute(
                "SELECT date(created_at,'+3 hours') AS day,COUNT(*) AS orders,"
                "COALESCE(SUM(CASE WHEN status!='cancelled' THEN subtotal_iqd ELSE 0 END),0) AS sales "
                "FROM orders WHERE created_at>=? AND created_at<? "
                "GROUP BY date(created_at,'+3 hours') ORDER BY day DESC", (since, until)
            )]
            best_sellers = [row_dict(r) for r in db.execute(
                "SELECT product_name_ar,SUM(quantity) AS quantity,SUM(line_total_iqd) AS sales "
                "FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.status!='cancelled' "
                "AND o.created_at>=? AND o.created_at<? "
                "GROUP BY product_name_ar ORDER BY quantity DESC LIMIT 10", (since, until)
            )]
            summary = row_dict(db.execute(
                "SELECT COUNT(*) AS orders,"
                "COALESCE(SUM(CASE WHEN status!='cancelled' THEN subtotal_iqd ELSE 0 END),0) AS sales,"
                "COALESCE(SUM(CASE WHEN status!='cancelled' AND delivery_fee_determined=1 "
                "THEN delivery_fee_iqd ELSE 0 END),0) AS delivery_fees,"
                "COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) AS cancelled,"
                "COALESCE(SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END),0) AS completed "
                "FROM orders WHERE created_at>=? AND created_at<?", (since, until)
            ).fetchone())
            payments = [row_dict(r) for r in db.execute(
                "SELECT payment_method,COUNT(*) AS orders,"
                "COALESCE(SUM(CASE WHEN payment_status='paid' THEN total_iqd ELSE 0 END),0) AS paid "
                "FROM orders WHERE created_at>=? AND created_at<? GROUP BY payment_method", (since, until)
            )]
        return self._json(200, {
            "period": period, "summary": summary, "daily": daily,
            "bestSellers": best_sellers, "payments": payments,
            "dateFrom": date_from, "dateTo": date_to,
        })

    def _admin_banners(self, method, ids):
        with database.connect() as db:
            if method == "GET":
                return self._json(200, [row_dict(r) for r in db.execute(
                    "SELECT * FROM promotional_banners ORDER BY sort_order,id"
                )])
            if method == "POST":
                data = self._body()
                title = require_text(data, "title", "عنوان الإعلان", 160)
                description = str(data.get("description", "")).strip()
                image_url = str(data.get("imageUrl", "")).strip()
                if len(description) > 1000 or len(image_url) > 1000 or (
                    image_url and not (
                        image_url.startswith("https://")
                        or (image_url.startswith("/") and not image_url.startswith("//"))
                    )
                ):
                    fail("بيانات الإعلان غير صحيحة.")
                cursor = db.execute(
                    "INSERT INTO promotional_banners (title_ar,description_ar,image_url,active,sort_order) "
                    "VALUES (?,?,?,?,?)",
                    (title, description, image_url, bool_value(data.get("active", True)),
                     safe_int(data.get("sortOrder", 0), "الترتيب", 0, 100000)),
                )
                db.commit()
                return self._json(201, {"id": cursor.lastrowid})
            if len(ids) != 1 or not ids[0].isdigit():
                fail("رقم الإعلان غير صحيح.")
            banner_id = int(ids[0])
            if method == "DELETE":
                db.execute("DELETE FROM promotional_banners WHERE id=?", (banner_id,))
                db.commit()
                return self._json(200, {"ok": True})
            if method == "PUT":
                data = self._body()
                title = require_text(data, "title", "عنوان الإعلان", 160)
                description = str(data.get("description", "")).strip()
                image_url = str(data.get("imageUrl", "")).strip()
                if len(description) > 1000 or len(image_url) > 1000 or (
                    image_url and not (
                        image_url.startswith("https://")
                        or (image_url.startswith("/") and not image_url.startswith("//"))
                    )
                ):
                    fail("بيانات الإعلان غير صحيحة.")
                db.execute(
                    "UPDATE promotional_banners SET title_ar=?,description_ar=?,image_url=?,active=?,sort_order=? "
                    "WHERE id=?",
                    (title, description, image_url, bool_value(data.get("active", True)),
                     safe_int(data.get("sortOrder", 0), "الترتيب", 0, 100000), banner_id),
                )
                db.commit()
                return self._json(200, {"ok": True})
        fail("الطريقة غير مدعومة.", 405)

    def _admin_staff(self, method, ids, current_user):
        if current_user["role"] != "admin":
            fail("هذه العملية متاحة لمدير النظام فقط.", 403)
        with database.connect() as db:
            if method == "GET":
                return self._json(200, [row_dict(r) for r in db.execute(
                    "SELECT id,username,role,active,created_at FROM staff_users ORDER BY id"
                )])
            if method == "POST":
                data = self._body()
                username = require_text(data, "username", "اسم المستخدم", 80)
                password = data.get("password")
                role = data.get("role")
                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):
                    fail("اسم المستخدم يجب أن يتكون من 3 إلى 80 حرفاً إنجليزياً أو رقماً.")
                if not isinstance(password, str) or len(password) < 12:
                    fail("كلمة المرور يجب ألا تقل عن 12 حرفاً.")
                if role not in ("manager", "staff", "admin"):
                    fail("الدور المحدد غير صحيح.")
                salt = secrets.token_bytes(16)
                digest = salt.hex() + hashlib.scrypt(
                    password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
                ).hex()
                try:
                    cursor = db.execute(
                        "INSERT INTO staff_users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
                        (username, digest, role, database.utc_now()),
                    )
                except sqlite3.IntegrityError:
                    fail("اسم المستخدم مستخدم مسبقاً.")
                db.commit()
                return self._json(201, {"id": cursor.lastrowid})
        fail("الطريقة غير مدعومة.", 405)

    def _print_order(self, order_id_value, data):
        order_id = safe_int(order_id_value, "الطلب", 1)
        target = data.get("target", "receipt")
        if target not in ("receipt", "kitchen"):
            fail("نوع الإيصال غير معروف.")
        with database.connect() as db:
            if get_setting(db, "printer_enabled") != "1":
                fail("الطابعة غير مفعّلة في الإعدادات.", 409)
            host = get_setting(db, "printer_host").strip()
            port = safe_int(get_setting(db, "printer_port", "9100"), "منفذ الطابعة", 1, 65535)
            width = get_setting(db, "printer_paper_width", "58")
            if not host:
                fail("يرجى ضبط عنوان طابعة الشبكة أولاً.", 409)
            order = db.execute(
                "SELECT o.*,c.full_name,c.phone FROM orders o JOIN customers c ON c.id=o.customer_id "
                "WHERE o.id=?", (order_id,)
            ).fetchone()
            if not order:
                fail("الطلب غير موجود.", 404)
            items = db.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
            business_name = get_setting(db, "business_name_ar", "حلويات ومعجنات فينتو")
        receipt = [
            business_name, "==============================",
            f"رقم الطلب: {order['order_number']}",
            datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        ]
        if target == "receipt":
            receipt += [
                f"الاسم: {order['full_name']}", f"الهاتف: {order['phone']}",
                f"العنوان: {order['delivery_area_name']} - {order['delivery_address']}",
            ]
        receipt.append("------------------------------")
        for item in items:
            receipt.append(f"{item['product_name_ar']} {item['variant_name_ar']}".strip())
            receipt.append(f"{item['quantity']} × {item['unit_price_iqd']:,} = {item['line_total_iqd']:,} د.ع")
        if target == "receipt":
            receipt += [
                "------------------------------",
                f"المجموع: {order['subtotal_iqd']:,} د.ع",
                f"التوصيل: {order['delivery_fee_iqd']:,} د.ع"
                if order["delivery_fee_determined"] else "التوصيل: يحدد لاحقاً",
                f"الإجمالي: {order['total_iqd']:,} د.ع"
                if order["delivery_fee_determined"] else "الإجمالي: يحدد لاحقاً",
                "الدفع: عند الاستلام",
            ]
            if order["delivery_instructions"]:
                receipt.append(f"ملاحظات: {order['delivery_instructions']}")
        elif order["delivery_instructions"]:
            receipt.append(f"ملاحظات التحضير: {order['delivery_instructions']}")
        receipt += ["", "", ""]
        columns = 32 if width == "58" else 48
        wrapped = [
            part
            for line in receipt
            for part in (textwrap.wrap(line, width=columns) or [""])
        ]
        payload = b"\x1b@" + "\n".join(wrapped).encode("utf-8") + b"\n\x1dV\x00"
        try:
            with socket.create_connection((host, port), timeout=4) as printer:
                printer.settimeout(4)
                printer.sendall(payload)
        except (OSError, UnicodeError) as error:
            print(f"Printer connection failed for order {order['order_number']}: {error}")
            fail("تعذر الاتصال بالطابعة. تحقق من اتصال الشبكة والعنوان والمنفذ.", 502)
        return self._json(200, {
            "ok": True, "bytesSent": len(payload), "paperWidth": width,
            "message": "أُرسلت بيانات الإيصال إلى الطابعة عبر شبكة ESC/POS.",
        })

    def _printer_test(self):
        with database.connect() as db:
            if get_setting(db, "printer_enabled") != "1":
                fail("فعّلوا الطابعة في الإعدادات أولاً.", 409)
            host = get_setting(db, "printer_host").strip()
            port = safe_int(get_setting(db, "printer_port", "9100"), "منفذ الطابعة", 1, 65535)
            if not host:
                fail("أدخلوا عنوان طابعة الشبكة أولاً.", 409)
            business_name = get_setting(db, "business_name_ar", "حلويات ومعجنات فينتو")
        payload = b"\x1b@" + f"{business_name}\nاختبار الاتصال بالطابعة\nVENTO ESC/POS\n\n\n".encode("utf-8") + b"\x1dV\x00"
        try:
            with socket.create_connection((host, port), timeout=4) as printer:
                printer.settimeout(4)
                printer.sendall(payload)
        except OSError as error:
            print(f"Printer test connection failed: {error}")
            fail("تعذر الاتصال بالطابعة. تحققوا من الشبكة والعنوان والمنفذ.", 502)
        return self._json(200, {
            "ok": True,
            "message": "أُرسلت ورقة اختبار إلى الطابعة. تحققوا من نتيجة الطباعة على الجهاز.",
        })

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def _handle(self):
        try:
            self._dispatch()
        except APIError as error:
            self._json(error.status, {"error": error.message})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as error:
            print(f"Unhandled request error: {error!r}")
            self._json(500, {"error": "حدث خطأ داخلي. يرجى المحاولة لاحقاً."})


def main():
    database.migrate()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    httpd = ThreadingHTTPServer((host, port), VenitoHandler)
    print(f"VENTO server listening on http://{host}:{port}")
    if not os.environ.get("ADMIN_USERNAME") or not os.environ.get("ADMIN_PASSWORD"):
        print("No initial admin created. Set ADMIN_USERNAME and ADMIN_PASSWORD before startup.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
