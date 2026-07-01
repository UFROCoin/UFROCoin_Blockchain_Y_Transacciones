"""
Tests de regresión para endpoints existentes.

Documenta la sección 6 del TRANSACTION_DETAIL_HANDOFF.md:
- GET /health debe seguir respondiendo {"status": "ok"}.
- GET /api/transactions/pending debe seguir listando transacciones pendientes.
- POST /api/transactions/ debe retornar la envoltura estándar {"status", "data"}.

Nota: GET /api/chain requiere mocks más complejos (BlockService con DB real)
y queda fuera del alcance inmediato de este handoff.
"""


# ---------------------------------------------------------------------------
# GET /health — Healthcheck
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """El endpoint de salud debe seguir funcionando correctamente."""

    def test_health_returns_200(self, test_client):
        """GET /health debe retornar status code 200."""
        response = test_client.get("/health")

        assert response.status_code == 200

    def test_health_body_is_status_ok(self, test_client):
        """GET /health debe retornar {"status": "ok"}."""
        response = test_client.get("/health")

        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/transactions/pending — Listar pendientes
# ---------------------------------------------------------------------------


class TestPendingTransactionsEndpoint:
    """El endpoint de transacciones pendientes no debe romperse."""

    def test_pending_returns_200(self, test_client, mock_transaction_service):
        """GET /api/transactions/pending debe retornar 200."""
        mock_transaction_service.get_pending_transactions = lambda: []

        response = test_client.get("/api/transactions/pending")

        assert response.status_code == 200

    def test_pending_body_structure(self, test_client, mock_transaction_service):
        """Debe retornar {"status": "ok", "data": [...]}."""
        mock_transaction_service.get_pending_transactions = lambda: []

        response = test_client.get("/api/transactions/pending")
        body = response.json()

        assert body["status"] == "ok"
        assert isinstance(body["data"], list)

    def test_pending_returns_transactions(self, test_client, mock_transaction_service):
        """Si hay transacciones pendientes, deben aparecer en data."""
        mock_transaction_service.get_pending_transactions = lambda: [
            {
                "id": "683f1a2b3c4d5e6f7a8b9c0d",
                "from": "sender_address",
                "to": "receiver_address",
                "amount": 10.0,
                "timestamp": "2026-06-03T22:45:00+00:00",
            }
        ]

        response = test_client.get("/api/transactions/pending")
        body = response.json()

        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "683f1a2b3c4d5e6f7a8b9c0d"


# ---------------------------------------------------------------------------
# POST /api/transactions/ — Crear transferencia
# ---------------------------------------------------------------------------


class TestCreateTransactionEndpoint:
    """El endpoint de creación debe retornar el contrato estándar."""

    def test_post_returns_wrapped_transaction_detail(
        self, test_client, mock_transaction_service
    ):
        """POST /api/transactions/ debe retornar {status, data} con id."""
        from_address = "a1b2c3d4e5f678901234567890abcdef12345678"
        to_address = "b1c2d3e4f5a678901234567890abcdef12345678"

        def create_transfer(payload):
            assert payload["from"] == from_address
            assert payload["to"] == to_address
            return {
                "_id": "683f1a2b3c4d5e6f7a8b9c0d",
                "from": from_address,
                "to": to_address,
                "amount": 25.0,
                "type": "TRANSFER",
                "status": "PENDING",
                "timestamp": "2026-06-29T12:00:00+00:00",
                "block_index": None,
            }

        mock_transaction_service.create_transfer = create_transfer

        response = test_client.post(
            "/api/transactions/",
            json={"from": from_address, "to": to_address, "amount": 25.0},
        )
        body = response.json()

        assert response.status_code == 201
        assert body["status"] == "ok"
        assert body["data"]["id"] == "683f1a2b3c4d5e6f7a8b9c0d"
        assert body["data"]["status"] == "PENDING"
        assert body["data"]["from"] == from_address
        assert body["data"]["to"] == to_address


# ---------------------------------------------------------------------------
# Verificación de que el nuevo endpoint no rompe el routing existente
# ---------------------------------------------------------------------------


class TestRoutingNotBroken:
    """El nuevo endpoint /{transaction_id} no debe interferir con /pending."""

    def test_pending_is_not_treated_as_transaction_id(
        self, test_client, mock_transaction_service
    ):
        """
        La ruta /api/transactions/pending NO debe interpretarse como
        /api/transactions/{transaction_id} con transaction_id='pending'.
        Debe seguir retornando la lista de pendientes.
        """
        mock_transaction_service.get_pending_transactions = lambda: []

        response = test_client.get("/api/transactions/pending")
        body = response.json()

        # Si se interpretó como /{transaction_id}, retornaría un 404 o un objeto
        # con 'code': 'TRANSACTION_NOT_FOUND'. Verificamos que NO es eso.
        assert body.get("code") != "TRANSACTION_NOT_FOUND"
        assert body["status"] == "ok"
        assert "data" in body
