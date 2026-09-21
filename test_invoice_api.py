import invoice_api


def test_missing_api_key_is_rejected():
    client = invoice_api.app.test_client()

    response = client.post(
        "/invoice",
        json={
            "invoice_id": "test-invoice-001",
            "customer_name": "Asha",
            "customer_email": "asha@example.com",
            "invoice_number": "TEST-001",
            "amount": 1000,
            "currency": "INR",
            "issue_date": "2026-09-01",
            "due_date": "2026-09-30",
            "status": "unpaid"
        }
    )

    assert response.status_code == 401


def test_negative_amount_is_rejected():
    client = invoice_api.app.test_client()

    response = client.post(
        "/invoice",
        headers={"X-API-Key": "invoice-demo-key-2026"},
        json={
            "invoice_id": "test-invoice-002",
            "customer_name": "Asha",
            "customer_email": "asha@example.com",
            "invoice_number": "TEST-002",
            "amount": -1000,
            "currency": "INR",
            "issue_date": "2026-09-01",
            "due_date": "2026-09-30",
            "status": "unpaid"
        }
    )

    assert response.status_code == 200
    assert response.json["status"] == "invalid"


def test_duplicate_invoice_is_rejected(monkeypatch):
    monkeypatch.setattr(invoice_api, "invoice_exists", lambda invoice_id: True)

    client = invoice_api.app.test_client()

    response = client.post(
        "/invoice",
        headers={"X-API-Key": "invoice-demo-key-2026"},
        json={
            "invoice_id": "test-invoice-003",
            "customer_name": "Asha",
            "customer_email": "asha@example.com",
            "invoice_number": "TEST-003",
            "amount": 1000,
            "currency": "INR",
            "issue_date": "2026-09-01",
            "due_date": "2026-09-30",
            "status": "unpaid"
        }
    )

    assert response.status_code == 200
    assert response.json["duplicate"] is True


def test_health_endpoint():
    client = invoice_api.app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
