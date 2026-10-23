from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import os
from pathlib import Path
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

import invoice_api


BASE_DATABASE_URL = os.environ.get("INVOICE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_DATABASE_URL,
    reason="Set INVOICE_TEST_DATABASE_URL to run PostgreSQL lifecycle tests",
)
API_HEADERS = {"X-API-Key": "invoice-demo-key-2026"}


@pytest.fixture()
def database(monkeypatch):
    schema = f"invoice_test_{uuid.uuid4().hex}"
    with psycopg.connect(BASE_DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    scoped_url = make_conninfo(BASE_DATABASE_URL, options=f"-c search_path={schema}")
    with psycopg.connect(scoped_url, autocommit=True) as connection:
        connection.execute(Path("init.sql").read_text(), prepare=False)

    monkeypatch.setattr(invoice_api, "DATABASE_URL", scoped_url)
    yield scoped_url

    with psycopg.connect(BASE_DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def create_unpaid_invoice(invoice_id, due_offset=1):
    today = date.today()
    with invoice_api.app.test_client() as client:
        response = client.post(
            "/invoice",
            headers=API_HEADERS,
            json={
                "invoice_id": invoice_id,
                "customer_name": "Synthetic Customer",
                "customer_email": f"{invoice_id}@example.com",
                "invoice_number": f"NUM-{invoice_id}",
                "amount": 12500,
                "currency": "INR",
                "issue_date": (today - timedelta(days=10)).isoformat(),
                "due_date": (today + timedelta(days=due_offset)).isoformat(),
                "status": "unpaid",
            },
        )
    assert response.status_code == 201


def create_invoice_response(invoice_id, due_offset=1):
    today = date.today()
    with invoice_api.app.test_client() as client:
        response = client.post(
            "/invoice",
            headers=API_HEADERS,
            json={
                "invoice_id": invoice_id,
                "customer_name": "Synthetic Customer",
                "customer_email": f"{invoice_id}@example.com",
                "invoice_number": f"NUM-{invoice_id}",
                "amount": 12500,
                "currency": "INR",
                "issue_date": (today - timedelta(days=10)).isoformat(),
                "due_date": (today + timedelta(days=due_offset)).isoformat(),
                "status": "unpaid",
            },
        )
        return response.status_code, response.get_json()


def run_reminder_claim():
    with invoice_api.app.test_client() as client:
        response = client.post(
            "/reminder-runs",
            headers=API_HEADERS,
            json={"dry_run": False},
        )
        return response.status_code, response.get_json()


def test_dry_run_does_not_create_ledger_rows(database):
    create_unpaid_invoice("dry-run-001")

    with invoice_api.app.test_client() as client:
        response = client.post(
            "/reminder-runs",
            headers=API_HEADERS,
            json={"dry_run": True},
        )

    assert response.status_code == 200
    assert response.json["candidate_count"] == 1
    assert response.json["queued_count"] == 0
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0] == 0


def test_concurrent_duplicate_invoice_intake_is_atomic(database):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_invoice_response("duplicate-001"), range(2)))

    assert sorted(status for status, _ in results) == [201, 409]
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 1


def test_concurrent_runs_queue_each_stage_once(database):
    create_unpaid_invoice("concurrent-001")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_reminder_claim(), range(2)))

    assert all(status == 200 for status, _ in results)
    assert sum(body["queued_count"] for _, body in results) == 1
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0] == 1

    status, repeated = run_reminder_claim()
    assert status == 200
    assert repeated["queued_count"] == 0


def test_payment_update_suppresses_queued_reminder(database):
    create_unpaid_invoice("paid-001")
    _, claimed = run_reminder_claim()
    reminder_id = claimed["reminders"][0]["reminder_id"]

    with invoice_api.app.test_client() as client:
        paid = client.patch(
            "/invoices/paid-001/status",
            headers=API_HEADERS,
            json={"status": "paid"},
        )
        outcome = client.patch(
            f"/reminder-events/{reminder_id}",
            headers=API_HEADERS,
            json={"status": "sent"},
        )

    assert paid.status_code == 200
    assert paid.json["queued_reminders_suppressed"] == 1
    assert outcome.status_code == 409
    with psycopg.connect(database) as connection:
        event_status = connection.execute(
            "SELECT status FROM reminder_events WHERE reminder_id = %s",
            (reminder_id,),
        ).fetchone()[0]
    assert event_status == "skipped"


def test_failed_delivery_can_be_requeued_and_sent(database):
    create_unpaid_invoice("retry-001", due_offset=-1)
    _, claimed = run_reminder_claim()
    reminder_id = claimed["reminders"][0]["reminder_id"]

    with invoice_api.app.test_client() as client:
        failed = client.patch(
            f"/reminder-events/{reminder_id}",
            headers=API_HEADERS,
            json={"status": "failed", "failure_code": "EMAIL_PROVIDER_TIMEOUT"},
        )
        retry = client.post(
            f"/reminder-events/{reminder_id}/retry",
            headers=API_HEADERS,
        )
        sent = client.patch(
            f"/reminder-events/{reminder_id}",
            headers=API_HEADERS,
            json={"status": "sent"},
        )
        summary = client.get("/reminder-events/summary", headers=API_HEADERS)

    assert failed.status_code == 200
    assert failed.json["attempt_count"] == 1
    assert retry.status_code == 200
    assert sent.status_code == 200
    assert sent.json["attempt_count"] == 2
    assert summary.status_code == 200
    assert summary.json["counts"] == {"sent": 1}
    assert summary.json["retryable_failed_count"] == 0


def test_terminal_invoice_cannot_be_reopened(database):
    create_unpaid_invoice("terminal-001")

    with invoice_api.app.test_client() as client:
        paid = client.patch(
            "/invoices/terminal-001/status",
            headers=API_HEADERS,
            json={"status": "paid"},
        )
        reopened = client.patch(
            "/invoices/terminal-001/status",
            headers=API_HEADERS,
            json={"status": "unpaid"},
        )
        reminders = client.get("/reminders", headers=API_HEADERS)

    assert paid.status_code == 200
    assert reopened.status_code == 409
    assert reminders.json["reminder_count"] == 0


def test_migration_upgrades_legacy_invoice_table():
    schema = f"invoice_migration_{uuid.uuid4().hex}"
    with psycopg.connect(BASE_DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    scoped_url = make_conninfo(BASE_DATABASE_URL, options=f"-c search_path={schema}")
    legacy_sql = """
        CREATE TABLE invoices (
            id SERIAL PRIMARY KEY,
            invoice_id TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            invoice_number TEXT UNIQUE NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            issue_date DATE NOT NULL,
            due_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'unpaid',
            reminder_count INTEGER NOT NULL DEFAULT 0,
            last_reminder_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """
    try:
        with psycopg.connect(scoped_url, autocommit=True) as connection:
            connection.execute(legacy_sql, prepare=False)
            connection.execute(
                Path("migrations/001_invoice_lifecycle.sql").read_text(),
                prepare=False,
            )
            columns = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'invoices'
                    """
                ).fetchall()
            }
            reminder_table = connection.execute(
                "SELECT to_regclass('reminder_events') IS NOT NULL"
            ).fetchone()[0]
        assert {"paid_at", "updated_at"}.issubset(columns)
        assert reminder_table is True
    finally:
        with psycopg.connect(BASE_DATABASE_URL, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
