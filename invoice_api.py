from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import os
import uuid

import psycopg
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "dbname=invoice_db"
)

INVOICE_API_KEY = os.environ.get(
    "INVOICE_API_KEY",
    "invoice-demo-key-2026"
)


def invoice_exists(invoice_id):
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM invoices WHERE invoice_id = %s",
                (invoice_id,)
            )
            return cursor.fetchone() is not None


def save_invoice(invoice):
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO invoices (
                    invoice_id,
                    customer_name,
                    customer_email,
                    invoice_number,
                    amount,
                    currency,
                    issue_date,
                    due_date,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    invoice["invoice_id"],
                    invoice["customer_name"],
                    invoice["customer_email"],
                    invoice["invoice_number"],
                    invoice["amount"],
                    invoice["currency"],
                    invoice["issue_date"],
                    invoice["due_date"],
                    invoice["status"]
                )
            )

            database_id = cursor.fetchone()[0]
            connection.commit()
            return database_id


def get_invoice_action(status, due_date):
    if status == "paid":
        return "No action required"

    today = date.today()
    days_until_due = (due_date - today).days

    if days_until_due < 0:
        return "Send overdue reminder and alert the finance team"

    if days_until_due <= 3:
        return "Send payment reminder"

    return "No reminder needed yet"


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.post("/invoice")
def create_invoice():
    provided_key = request.headers.get("X-API-Key")

    if provided_key != INVOICE_API_KEY:
        return jsonify({
            "received": False,
            "error": "Unauthorized"
        }), 401

    data = request.get_json() or {}

    invoice_id = data.get("invoice_id") or str(uuid.uuid4())
    customer_name = data.get("customer_name", "").strip()
    customer_email = data.get("customer_email", "").strip().lower()
    invoice_number = data.get("invoice_number", "").strip()
    currency = data.get("currency", "INR").strip().upper()
    status = data.get("status", "unpaid").strip().lower()

    try:
        amount = Decimal(str(data.get("amount", "")))
        issue_date = datetime.strptime(
            data.get("issue_date", ""),
            "%Y-%m-%d"
        ).date()
        due_date = datetime.strptime(
            data.get("due_date", ""),
            "%Y-%m-%d"
        ).date()
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Amount and dates must use valid formats"
        }), 200

    if not customer_name or not customer_email or not invoice_number:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Customer name, email, and invoice number are required"
        }), 200

    if amount <= 0:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Amount must be greater than zero"
        }), 200

    if due_date < issue_date:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Due date cannot be before issue date"
        }), 200

    if invoice_exists(invoice_id):
        return jsonify({
            "received": False,
            "duplicate": True,
            "invoice_id": invoice_id,
            "message": "This invoice was already processed"
        }), 200

    invoice = {
        "invoice_id": invoice_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "invoice_number": invoice_number,
        "amount": str(amount),
        "currency": currency,
        "issue_date": issue_date.isoformat(),
        "due_date": due_date.isoformat(),
        "status": status,
        "recommended_action": get_invoice_action(status, due_date)
    }

    database_id = save_invoice(invoice)

    return jsonify({
        "received": True,
        "saved": True,
        "database_id": database_id,
        "invoice": invoice
    }), 200

@app.get("/reminders")
def check_reminders():
    provided_key = request.headers.get("X-API-Key")

    if provided_key != INVOICE_API_KEY:
        return jsonify({
            "received": False,
            "error": "Unauthorized"
        }), 401

    today = date.today()
    reminder_cutoff = today.fromordinal(today.toordinal() + 3)

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    invoice_id,
                    customer_name,
                    customer_email,
                    invoice_number,
                    amount,
                    currency,
                    issue_date,
                    due_date,
                    status
                FROM invoices
                WHERE status = 'unpaid'
                  AND due_date <= %s
                ORDER BY due_date
                """,
                (reminder_cutoff,)
            )

            rows = cursor.fetchall()

    reminders = []

    for row in rows:
        (
            invoice_id,
            customer_name,
            customer_email,
            invoice_number,
            amount,
            currency,
            issue_date,
            due_date,
            status
        ) = row

        if due_date < today:
            action = "Send overdue reminder and alert the finance team"
        else:
            action = "Send payment reminder"

        reminders.append({
            "invoice_id": invoice_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "invoice_number": invoice_number,
            "amount": str(amount),
            "currency": currency,
            "issue_date": issue_date.isoformat(),
            "due_date": due_date.isoformat(),
            "status": status,
            "recommended_action": action
        })

    return jsonify({
        "received": True,
        "reminder_count": len(reminders),
        "reminders": reminders
    }), 200
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5080, debug=True)
