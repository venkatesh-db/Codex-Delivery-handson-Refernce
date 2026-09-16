"""Retail invoice web app. Run with: python3 app.py"""

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("BILLING_DB", ROOT / "billing.sqlite3"))
MAX_BODY = 64 * 1024
MAX_WORKERS = 16
CENT = Decimal("0.01")


class IdempotencyConflict(Exception):
    pass


def connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                currency TEXT NOT NULL DEFAULT 'USD',
                customer_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                tax_rate TEXT NOT NULL,
                subtotal_cents INTEGER NOT NULL,
                tax_cents INTEGER NOT NULL,
                total_cents INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                product_name TEXT NOT NULL,
                quantity TEXT NOT NULL,
                unit_price_cents INTEGER NOT NULL,
                line_total_cents INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoice_discounts (
                invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id),
                discount_rate TEXT NOT NULL,
                discount_cents INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoice_requests (
                idempotency_key TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL,
                invoice_id INTEGER NOT NULL UNIQUE REFERENCES invoices(id)
            );
        """)


def decimal_value(value, name, *, zero_ok=False, max_value=Decimal("1000000")):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{name} must be a number") from None
    if not number.is_finite() or number < 0 or (number == 0 and not zero_ok) or number > max_value:
        raise ValueError(f"{name} is out of range")
    return number


def cents(value):
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def prepare_invoice(data):
    if not isinstance(data, dict):
        raise ValueError("Invoice must be an object")
    customer = data.get("customer_name")
    if not isinstance(customer, str) or not customer.strip() or len(customer.strip()) > 120:
        raise ValueError("Customer name is required (maximum 120 characters)")
    tax_rate = decimal_value(data.get("tax_rate", 0), "Tax rate", zero_ok=True, max_value=Decimal("100"))
    if tax_rate.as_tuple().exponent < -2:
        raise ValueError("Tax rate supports up to 2 decimal places")
    discount_rate = decimal_value(data.get("discount_rate", 0), "Discount rate", zero_ok=True, max_value=Decimal("100"))
    if discount_rate.as_tuple().exponent < -2:
        raise ValueError("Discount rate supports up to 2 decimal places")
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValueError("Add between 1 and 100 items")
    prepared = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {index} must be an object")
        name = item.get("product_name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError(f"Item {index}: product name is required (maximum 120 characters)")
        quantity = decimal_value(item.get("quantity"), f"Item {index} quantity")
        price = decimal_value(item.get("unit_price"), f"Item {index} unit price", zero_ok=True)
        if quantity.as_tuple().exponent < -3:
            raise ValueError(f"Item {index} quantity supports up to 3 decimal places")
        if price.as_tuple().exponent < -2:
            raise ValueError(f"Item {index} unit price supports up to 2 decimal places")
        price_cents = cents(price)
        line_cents = int((quantity * price_cents).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        prepared.append((name.strip(), str(quantity), price_cents, line_cents))
    subtotal = sum(row[3] for row in prepared)
    if subtotal > 1_000_000_000_00:
        raise ValueError("Invoice total is too large")
    discount = int((Decimal(subtotal) * discount_rate / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    taxable_subtotal = subtotal - discount
    tax = int((Decimal(taxable_subtotal) * tax_rate / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return customer.strip(), str(tax_rate), str(discount_rate), prepared, subtotal, discount, tax


def fetch_invoice(db, invoice_id):
    invoice = db.execute(
        """
        SELECT invoices.*,
               COALESCE(invoice_discounts.discount_rate, '0') AS discount_rate,
               COALESCE(invoice_discounts.discount_cents, 0) AS discount_cents
        FROM invoices
        LEFT JOIN invoice_discounts ON invoice_discounts.invoice_id = invoices.id
        WHERE invoices.id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if invoice is None:
        return None
    items = db.execute("SELECT product_name, quantity, unit_price_cents, line_total_cents FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,)).fetchall()
    return {**dict(invoice), "items": [dict(item) for item in items]}


def normalize_idempotency_key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Idempotency-Key header is required")
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        raise ValueError("Idempotency-Key header must be a UUID") from None


def invoice_fingerprint(customer, tax_rate, discount_rate, items):
    fingerprint_data = {"customer_name": customer, "tax_rate": tax_rate, "items": items}
    discount_number = Decimal(discount_rate)
    if discount_number != 0:
        fingerprint_data["discount_rate"] = format(discount_number.normalize(), "f")
    canonical = json.dumps(
        fingerprint_data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fetch_invoice_request(db, idempotency_key):
    return db.execute(
        "SELECT request_fingerprint, invoice_id FROM invoice_requests WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()


def create_invoice(data, idempotency_key):
    idempotency_key = normalize_idempotency_key(idempotency_key)
    customer, tax_rate, discount_rate, items, subtotal, discount, tax = prepare_invoice(data)
    request_fingerprint = invoice_fingerprint(customer, tax_rate, discount_rate, items)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing_request = fetch_invoice_request(db, idempotency_key)
        if existing_request is not None:
            if existing_request["request_fingerprint"] != request_fingerprint:
                raise IdempotencyConflict("Idempotency-Key was already used for a different invoice")
            return fetch_invoice(db, existing_request["invoice_id"]), True
        cursor = db.execute(
            "INSERT INTO invoices (currency, customer_name, created_at, tax_rate, subtotal_cents, tax_cents, total_cents) VALUES ('USD', ?, ?, ?, ?, ?, ?)",
            (customer, datetime.now(timezone.utc).isoformat(), tax_rate, subtotal, tax, subtotal - discount + tax),
        )
        db.executemany(
            "INSERT INTO invoice_items (invoice_id, product_name, quantity, unit_price_cents, line_total_cents) VALUES (?, ?, ?, ?, ?)",
            [(cursor.lastrowid, *item) for item in items],
        )
        db.execute(
            "INSERT INTO invoice_discounts (invoice_id, discount_rate, discount_cents) VALUES (?, ?, ?)",
            (cursor.lastrowid, discount_rate, discount),
        )
        db.execute(
            "INSERT INTO invoice_requests (idempotency_key, request_fingerprint, invoice_id) VALUES (?, ?, ?)",
            (idempotency_key, request_fingerprint, cursor.lastrowid),
        )
        return fetch_invoice(db, cursor.lastrowid), False


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = MAX_WORKERS

    def __init__(self, server_address, request_handler_class, max_workers=MAX_WORKERS):
        self.worker_slots = threading.BoundedSemaphore(max_workers)
        super().__init__(server_address, request_handler_class)

    def process_request(self, request, client_address):
        self.worker_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.worker_slots.release()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/invoices":
            with connect() as db:
                rows = db.execute("SELECT id, customer_name, created_at, total_cents FROM invoices ORDER BY id DESC LIMIT 50").fetchall()
                self.send_json(200, [dict(row) for row in rows])
        elif path.startswith("/api/invoices/") and path.removeprefix("/api/invoices/").isdigit():
            with connect() as db:
                invoice = fetch_invoice(db, int(path.rsplit("/", 1)[1]))
            self.send_json(200, invoice) if invoice else self.send_json(404, {"error": "Invoice not found"})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/invoices":
            return self.send_json(404, {"error": "Not found"})
        try:
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                return self.send_json(415, {"error": "Use application/json"})
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request body must be 1–65536 bytes"})
            data = json.loads(self.rfile.read(length))
            invoice, replayed = create_invoice(data, self.headers.get("Idempotency-Key"))
        except IdempotencyConflict as exc:
            return self.send_json(409, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc)})
        except sqlite3.Error:
            return self.send_json(503, {"error": "Invoice could not be saved; please retry"})
        self.send_json(200 if replayed else 201, invoice)


if __name__ == "__main__":
    init_db()
    host = os.environ.get("BILLING_HOST", "127.0.0.1")
    port = int(os.environ.get("BILLING_PORT", "8000"))
    print(f"Billing app: http://{host}:{port}")
    BoundedThreadingHTTPServer((host, port), Handler).serve_forever()
