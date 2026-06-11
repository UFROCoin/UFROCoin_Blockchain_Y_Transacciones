"""
Tests de integración HTTP para el endpoint GET /api/transactions/{transaction_id}.

Cubren los escenarios del TRANSACTION_DETAIL_HANDOFF.md § 3:
- Respuesta 200 con transacción pendiente.
- Respuesta 200 con transacción confirmada.
- Respuesta 404 con código TRANSACTION_NOT_FOUND.
- Validación de que todos los campos están presentes en la respuesta.
- Validación de que se usan los alias `from` y `to` (no `sender`/`receiver`).
"""

from conftest import VALID_OBJECT_ID, NONEXISTENT_OBJECT_ID


# ---------------------------------------------------------------------------
# GET /api/transactions/{id} — 200 Transacción pendiente
# ---------------------------------------------------------------------------


class TestGetTransactionEndpoint200Pending:
    """Endpoint retorna 200 con una transacción pendiente del mempool."""

    def test_status_code_200(self, test_client, mock_transaction_service):
        """Debe responder con status 200."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 25.0,
            "type": "TRANSFER",
            "status": "PENDING",
            "timestamp": "2026-06-03T22:45:00+00:00",
            "block_index": None,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")

        assert response.status_code == 200

    def test_response_body_structure(self, test_client, mock_transaction_service):
        """Debe retornar {status: 'ok', data: {...}}."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 25.0,
            "type": "TRANSFER",
            "status": "PENDING",
            "timestamp": "2026-06-03T22:45:00+00:00",
            "block_index": None,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")
        body = response.json()

        assert body["status"] == "ok"
        assert "data" in body

    def test_pending_transaction_fields(self, test_client, mock_transaction_service):
        """Transacción pendiente: status=PENDING y block_index=null."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 25.0,
            "type": "TRANSFER",
            "status": "PENDING",
            "timestamp": "2026-06-03T22:45:00+00:00",
            "block_index": None,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")
        data = response.json()["data"]

        assert data["status"] == "PENDING"
        assert data["block_index"] is None


# ---------------------------------------------------------------------------
# GET /api/transactions/{id} — 200 Transacción confirmada
# ---------------------------------------------------------------------------


class TestGetTransactionEndpoint200Confirmed:
    """Endpoint retorna 200 con una transacción confirmada en un bloque."""

    def test_confirmed_transaction_has_block_index(
        self, test_client, mock_transaction_service
    ):
        """Transacción confirmada: status=CONFIRMED y block_index=N."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 50.0,
            "type": "TRANSFER",
            "status": "CONFIRMED",
            "timestamp": "2026-06-02T10:00:00+00:00",
            "block_index": 3,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "CONFIRMED"
        assert data["block_index"] == 3


# ---------------------------------------------------------------------------
# GET /api/transactions/{id} — 404 No encontrada
# ---------------------------------------------------------------------------


class TestGetTransactionEndpoint404:
    """Endpoint retorna 404 cuando la transacción no existe."""

    def test_status_code_404(self, test_client, mock_transaction_service):
        """Debe responder con status 404."""
        mock_transaction_service.get_transaction_by_id = lambda _: None

        response = test_client.get(f"/api/transactions/{NONEXISTENT_OBJECT_ID}")

        assert response.status_code == 404

    def test_error_body_structure(self, test_client, mock_transaction_service):
        """Debe retornar {status: 'error', code: 'TRANSACTION_NOT_FOUND', message: ...}."""
        mock_transaction_service.get_transaction_by_id = lambda _: None

        response = test_client.get(f"/api/transactions/{NONEXISTENT_OBJECT_ID}")
        body = response.json()

        assert body["status"] == "error"
        assert body["code"] == "TRANSACTION_NOT_FOUND"
        assert body["message"] == "Transaction not found"


# ---------------------------------------------------------------------------
# Validación de campos completos en la respuesta
# ---------------------------------------------------------------------------


class TestResponseContainsAllFields:
    """La respuesta 200 contiene todos los campos del modelo TransactionDetail."""

    EXPECTED_FIELDS = {"id", "from", "to", "amount", "type", "status", "timestamp", "block_index"}

    def test_all_fields_present(self, test_client, mock_transaction_service):
        """Verifica que cada campo documentado en el handoff esté en la respuesta."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 25.0,
            "type": "TRANSFER",
            "status": "PENDING",
            "timestamp": "2026-06-03T22:45:00+00:00",
            "block_index": None,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")
        data = response.json()["data"]

        assert set(data.keys()) == self.EXPECTED_FIELDS


# ---------------------------------------------------------------------------
# Validación de aliases Pydantic (from/to en lugar de sender/receiver)
# ---------------------------------------------------------------------------


class TestResponseUsesAliases:
    """Los campos se serializan con los aliases from/to, no sender/receiver."""

    def test_uses_from_not_sender(self, test_client, mock_transaction_service):
        """El campo debe llamarse 'from', no 'sender'."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 25.0,
            "type": "TRANSFER",
            "status": "PENDING",
            "timestamp": "2026-06-03T22:45:00+00:00",
            "block_index": None,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")
        data = response.json()["data"]

        assert "from" in data
        assert "sender" not in data

    def test_uses_to_not_receiver(self, test_client, mock_transaction_service):
        """El campo debe llamarse 'to', no 'receiver'."""
        mock_transaction_service.get_transaction_by_id = lambda _: {
            "id": VALID_OBJECT_ID,
            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
            "amount": 25.0,
            "type": "TRANSFER",
            "status": "PENDING",
            "timestamp": "2026-06-03T22:45:00+00:00",
            "block_index": None,
        }

        response = test_client.get(f"/api/transactions/{VALID_OBJECT_ID}")
        data = response.json()["data"]

        assert "to" in data
        assert "receiver" not in data
