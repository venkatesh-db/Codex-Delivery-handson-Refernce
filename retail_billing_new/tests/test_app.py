import json
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = app.DB_PATH
        app.DB_PATH = Path(self.temp.name) / "test.sqlite3"
        app.init_db()

    def tearDown(self):
        app.DB_PATH = self.original_db
        self.temp.cleanup()

    def create_invoice(self, data, idempotency_key=None):
        invoice, replayed = app.create_invoice(data, idempotency_key or str(uuid.uuid4()))
        self.assertFalse(replayed)
        return invoice

    def test_invoice_persists_product_lines_and_server_totals(self):
        invoice = self.create_invoice({
            "customer_name": "Ada",
            "tax_rate": "10",
            "discount_rate": "10",
            "total_cents": 1,
            "items": [
                {"product_name": "Widget", "quantity": "2", "unit_price": "12.50"},
                {"product_name": "Service", "quantity": "1.5", "unit_price": "2.00"},
            ],
        })
        self.assertEqual(
            (invoice["subtotal_cents"], invoice["discount_cents"], invoice["tax_cents"], invoice["total_cents"]),
            (2800, 280, 252, 2772),
        )
        self.assertEqual(invoice["discount_rate"], "10")
        self.assertEqual(len(invoice["items"]), 2)
        with app.connect() as db:
            self.assertEqual(app.fetch_invoice(db, invoice["id"]), invoice)

    def test_bad_item_does_not_create_invoice(self):
        with self.assertRaisesRegex(ValueError, "out of range"):
            self.create_invoice({"customer_name": "Ada", "items": [{"product_name": "Widget", "quantity": "-1", "unit_price": "2"}]})
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)

    def test_rounding_and_saved_snapshot(self):
        invoice = self.create_invoice({"customer_name": "Ada", "tax_rate": "8.25", "items": [
            {"product_name": "Bulk rice", "quantity": "0.125", "unit_price": "0.04"},
            {"product_name": "Tea", "quantity": "1", "unit_price": "0.06"},
        ]})
        self.assertEqual([item["line_total_cents"] for item in invoice["items"]], [1, 6])
        self.assertEqual((invoice["subtotal_cents"], invoice["tax_cents"], invoice["total_cents"]), (7, 1, 8))
        self.assertEqual(invoice["currency"], "USD")
        with app.connect() as fresh_db:
            self.assertEqual(app.fetch_invoice(fresh_db, invoice["id"]), invoice)

    def test_discount_and_tax_round_half_up_at_cent_boundaries(self):
        invoice = self.create_invoice({
            "customer_name": "Ada",
            "tax_rate": "12.5",
            "discount_rate": "10",
            "items": [{"product_name": "Sample", "quantity": "1", "unit_price": "0.05"}],
        })
        self.assertEqual(
            (invoice["subtotal_cents"], invoice["discount_cents"], invoice["tax_cents"], invoice["total_cents"]),
            (5, 1, 1, 5),
        )

    def test_discount_boundaries_and_validation(self):
        for rate in ("0", "100", "12.34"):
            with self.subTest(valid_rate=rate):
                invoice = self.create_invoice({
                    "customer_name": "Ada",
                    "discount_rate": rate,
                    "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}],
                })
                self.assertEqual(invoice["discount_rate"], rate)

        invalid_rates = ("-0.01", "100.01", "1.001", None, True, "NaN", "Infinity")
        for rate in invalid_rates:
            with self.subTest(invalid_rate=rate), self.assertRaises(ValueError):
                self.create_invoice({
                    "customer_name": "Ada",
                    "discount_rate": rate,
                    "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}],
                })
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoice_discounts").fetchone()[0], 3)

    def test_full_discount_produces_zero_tax_and_total(self):
        invoice = self.create_invoice({
            "customer_name": "Ada",
            "tax_rate": "25",
            "discount_rate": "100",
            "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}],
        })
        self.assertEqual((invoice["discount_cents"], invoice["tax_cents"], invoice["total_cents"]), (100, 0, 0))

    def test_failed_line_insert_rolls_back_header(self):
        with app.connect() as db:
            db.execute("CREATE TRIGGER reject_line BEFORE INSERT ON invoice_items BEGIN SELECT RAISE(ABORT, 'line rejected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_invoice({"customer_name": "Ada", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}]})
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoice_items").fetchone()[0], 0)

    def test_http_create_list_and_get(self):
        server = app.BoundedThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/") as response:
                self.assertEqual(response.status, 200)
                html = response.read()
                self.assertIn(b'id="invoice-form"', html)
                self.assertIn(b'id="discount"', html)
                self.assertIn(b'id="discount-amount"', html)
            payload = json.dumps({"customer_name": "Ada", "tax_rate": "10", "discount_rate": "10", "items": [{"product_name": "Widget", "quantity": "2", "unit_price": "12.50"}]}).encode()
            idempotency_key = str(uuid.uuid4())
            request = Request(base + "/api/invoices", data=payload, headers={"Content-Type": "application/json", "Idempotency-Key": idempotency_key}, method="POST")
            with urlopen(request) as response:
                self.assertEqual(response.status, 201)
                saved = json.load(response)
            replay = Request(base + "/api/invoices", data=payload, headers={"Content-Type": "application/json", "Idempotency-Key": idempotency_key}, method="POST")
            with urlopen(replay) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), saved)
            conflicting_payload = json.dumps({"customer_name": "Ada", "tax_rate": "10", "discount_rate": "20", "items": [{"product_name": "Widget", "quantity": "2", "unit_price": "12.50"}]}).encode()
            conflict = Request(base + "/api/invoices", data=conflicting_payload, headers={"Content-Type": "application/json", "Idempotency-Key": idempotency_key}, method="POST")
            with self.assertRaises(HTTPError) as conflict_response:
                urlopen(conflict)
            self.assertEqual(conflict_response.exception.code, 409)
            conflict_response.exception.close()
            for headers in (
                {"Content-Type": "application/json"},
                {"Content-Type": "application/json", "Idempotency-Key": "not-a-uuid"},
            ):
                with self.subTest(headers=headers), self.assertRaises(HTTPError) as key_response:
                    urlopen(Request(base + "/api/invoices", data=payload, headers=headers, method="POST"))
                self.assertEqual(key_response.exception.code, 400)
                key_response.exception.close()
            self.assertEqual((saved["discount_cents"], saved["tax_cents"], saved["total_cents"]), (250, 225, 2475))
            with urlopen(base + "/api/invoices") as response:
                self.assertEqual(json.load(response)[0]["id"], saved["id"])
            with urlopen(base + f"/api/invoices/{saved['id']}") as response:
                self.assertEqual(json.load(response), saved)
            bad = json.dumps({"customer_name": "Ada", "items": [{"product_name": "Broken", "quantity": "0", "unit_price": "1.00"}]}).encode()
            with self.assertRaises(HTTPError) as bad_response:
                urlopen(Request(base + "/api/invoices", data=bad, headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}, method="POST"))
            self.assertEqual(bad_response.exception.code, 400)
            bad_response.exception.close()
            invalid_discount = json.dumps({"customer_name": "Ada", "discount_rate": "1.001", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}]}).encode()
            with self.assertRaises(HTTPError) as discount_response:
                urlopen(Request(base + "/api/invoices", data=invalid_discount, headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}, method="POST"))
            self.assertEqual(discount_response.exception.code, 400)
            discount_response.exception.close()
            with app.connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)
            with self.assertRaises(HTTPError) as context:
                urlopen(base + "/api/invoices/999")
            self.assertEqual(context.exception.code, 404)
            context.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_idempotency_replay_and_conflict(self):
        payload = {"customer_name": "Ada", "tax_rate": "10", "items": [{"product_name": "Widget", "quantity": "1", "unit_price": "10.00"}]}
        idempotency_key = str(uuid.uuid4())
        first, replayed = app.create_invoice(payload, idempotency_key)
        self.assertFalse(replayed)
        second, replayed = app.create_invoice(payload, idempotency_key.upper())
        self.assertTrue(replayed)
        self.assertEqual(second, first)
        with app.connect() as fresh_db:
            self.assertEqual(app.fetch_invoice(fresh_db, first["id"]), first)
            self.assertEqual(fresh_db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)
            self.assertEqual(fresh_db.execute("SELECT COUNT(*) FROM invoice_requests").fetchone()[0], 1)
        changed = {**payload, "customer_name": "Grace"}
        with self.assertRaisesRegex(app.IdempotencyConflict, "different invoice"):
            app.create_invoice(changed, idempotency_key)
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)

    def test_discount_idempotency_and_legacy_zero_discount_replay(self):
        payload = {"customer_name": "Ada", "tax_rate": "10", "discount_rate": "12.5", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "10.00"}]}
        idempotency_key = str(uuid.uuid4())
        first, replayed = app.create_invoice(payload, idempotency_key)
        self.assertFalse(replayed)
        second, replayed = app.create_invoice({**payload, "discount_rate": "12.50"}, idempotency_key)
        self.assertTrue(replayed)
        self.assertEqual(second, first)
        with self.assertRaises(app.IdempotencyConflict):
            app.create_invoice({**payload, "discount_rate": "12.6"}, idempotency_key)

        legacy_payload = {"customer_name": "Grace", "tax_rate": "5", "items": [{"product_name": "Rice", "quantity": "1", "unit_price": "2.00"}]}
        legacy_key = str(uuid.uuid4())
        legacy_invoice, _ = app.create_invoice(legacy_payload, legacy_key)
        with app.connect() as db:
            db.execute("DELETE FROM invoice_discounts WHERE invoice_id = ?", (legacy_invoice["id"],))
        replay, replayed = app.create_invoice({**legacy_payload, "discount_rate": "0.00"}, legacy_key)
        self.assertTrue(replayed)
        self.assertEqual((replay["discount_rate"], replay["discount_cents"]), ("0", 0))
        self.assertEqual((replay["tax_cents"], replay["total_cents"]), (10, 210))

    def test_legacy_invoice_without_discount_preserves_stored_totals(self):
        with app.connect() as db:
            cursor = db.execute(
                "INSERT INTO invoices (currency, customer_name, created_at, tax_rate, subtotal_cents, tax_cents, total_cents) VALUES ('USD', 'Legacy', '2026-01-01T00:00:00+00:00', '10', 100, 10, 110)"
            )
            db.execute(
                "INSERT INTO invoice_items (invoice_id, product_name, quantity, unit_price_cents, line_total_cents) VALUES (?, 'Tea', '1', 100, 100)",
                (cursor.lastrowid,),
            )
            invoice_id = cursor.lastrowid
        with app.connect() as fresh_db:
            invoice = app.fetch_invoice(fresh_db, invoice_id)
        self.assertEqual((invoice["discount_rate"], invoice["discount_cents"]), ("0", 0))
        self.assertEqual((invoice["subtotal_cents"], invoice["tax_cents"], invoice["total_cents"]), (100, 10, 110))

    def test_concurrent_retries_create_one_invoice(self):
        payload = {"customer_name": "Ada", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}]}
        idempotency_key = str(uuid.uuid4())
        start = threading.Barrier(3)
        results = []
        errors = []

        def create():
            start.wait()
            try:
                results.append(app.create_invoice(payload, idempotency_key))
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=create) for _ in range(2)]
        for worker in workers:
            worker.start()
        start.wait()
        for worker in workers:
            worker.join(10)
        self.assertFalse(errors)
        self.assertEqual(len(results), 2)
        self.assertEqual({invoice["id"] for invoice, replayed in results}, {1})
        self.assertEqual(sorted(replayed for invoice, replayed in results), [False, True])
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoice_items").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoice_requests").fetchone()[0], 1)

    def test_invalid_idempotency_keys_do_not_write(self):
        payload = {"customer_name": "Ada", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}]}
        for key in (None, "", "not-a-uuid"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Idempotency-Key"):
                app.create_invoice(payload, key)
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)

    def test_failed_request_mapping_rolls_back_invoice(self):
        with app.connect() as db:
            db.execute("CREATE TRIGGER reject_request BEFORE INSERT ON invoice_requests BEGIN SELECT RAISE(ABORT, 'request rejected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            app.create_invoice(
                {"customer_name": "Ada", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}]},
                str(uuid.uuid4()),
            )
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoice_items").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoice_requests").fetchone()[0], 0)

    def test_failed_discount_insert_rolls_back_invoice(self):
        with app.connect() as db:
            db.execute("CREATE TRIGGER reject_discount BEFORE INSERT ON invoice_discounts BEGIN SELECT RAISE(ABORT, 'discount rejected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            app.create_invoice(
                {"customer_name": "Ada", "discount_rate": "10", "items": [{"product_name": "Tea", "quantity": "1", "unit_price": "1.00"}]},
                str(uuid.uuid4()),
            )
        with app.connect() as db:
            for table in ("invoices", "invoice_items", "invoice_discounts", "invoice_requests"):
                with self.subTest(table=table):
                    self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)


class ConcurrencyTests(unittest.TestCase):
    def test_server_runs_at_most_sixteen_handlers(self):
        class BlockingHandler(BaseHTTPRequestHandler):
            active = 0
            maximum_active = 0
            completed = 0
            lock = threading.Lock()
            sixteen_active = threading.Event()
            release = threading.Event()

            def do_GET(self):
                with self.lock:
                    type(self).active += 1
                    type(self).maximum_active = max(type(self).maximum_active, type(self).active)
                    if type(self).active == app.MAX_WORKERS:
                        type(self).sixteen_active.set()
                type(self).release.wait(5)
                self.send_response(204)
                self.end_headers()
                with self.lock:
                    type(self).active -= 1
                    type(self).completed += 1

            def log_message(self, format, *args):
                pass

        server = app.BoundedThreadingHTTPServer(("127.0.0.1", 0), BlockingHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        errors = []

        def request():
            try:
                with urlopen(url, timeout=10) as response:
                    self.assertEqual(response.status, 204)
            except Exception as exc:
                errors.append(exc)

        clients = [threading.Thread(target=request, daemon=True) for _ in range(app.MAX_WORKERS + 1)]
        try:
            for client in clients:
                client.start()
            self.assertTrue(BlockingHandler.sixteen_active.wait(5))
            time.sleep(0.1)
            self.assertEqual(BlockingHandler.maximum_active, app.MAX_WORKERS)
            BlockingHandler.release.set()
            for client in clients:
                client.join(10)
            self.assertFalse(errors)
            self.assertEqual(BlockingHandler.completed, app.MAX_WORKERS + 1)
        finally:
            BlockingHandler.release.set()
            server.shutdown()
            server.server_close()
            server_thread.join()


if __name__ == "__main__":
    unittest.main()
