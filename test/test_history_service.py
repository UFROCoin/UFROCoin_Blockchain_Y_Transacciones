"""
Tests unitarios para src.services.history_service.get_wallet_history.

Estrategia:
- Se mockean get_transactions_collection y get_blocks_collection para
  aislar la función de MongoDB.
- Se verifica el enriquecimiento de estado, paginación y ordenamiento.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper para construir mocks de colecciones
# ---------------------------------------------------------------------------


def make_collections(pending_txs: list[dict], blocks: list[dict]):
    """
    Construye mocks de las colecciones MongoDB necesarias para history_service.

    Parámetros:
        pending_txs: documentos a retornar por transactions_collection.find(query).
        blocks: documentos a retornar por blocks_collection.find(query).
    """
    tx_col = MagicMock()
    tx_col.find.return_value = iter(pending_txs)

    block_col = MagicMock()
    block_col.find.return_value = iter(blocks)

    return tx_col, block_col


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetWalletHistory:
    """Tests para get_wallet_history."""

    TARGET_ADDRESS = "wallet_abc"

    def _call(self, pending_txs, blocks, page=1, limit=10):
        """Invoca get_wallet_history con las colecciones mockeadas."""
        tx_col, block_col = make_collections(pending_txs, blocks)

        with (
            patch("src.services.history_service.get_transactions_collection", return_value=tx_col),
            patch("src.services.history_service.get_blocks_collection", return_value=block_col),
        ):
            from src.services.history_service import get_wallet_history
            return get_wallet_history(self.TARGET_ADDRESS, page=page, limit=limit)

    def test_returns_empty_list_when_no_history(self):
        """Una dirección sin actividad debe retornar lista vacía."""
        result = self._call(pending_txs=[], blocks=[])
        assert result == []

    def test_pending_tx_from_address_appears(self):
        """Una transacción pendiente en la que la dirección es emisora aparece en el historial."""
        pending = [
            {
                "_id": "id-001",
                "from": self.TARGET_ADDRESS,
                "to": "other_wallet",
                "amount": 50.0,
                "timestamp": "2026-06-01T10:00:00Z",
                "status": "PENDING",
            }
        ]
        result = self._call(pending_txs=pending, blocks=[])
        assert len(result) == 1
        assert result[0]["from"] == self.TARGET_ADDRESS
        assert result[0]["status"] == "PENDING"

    def test_pending_tx_to_address_appears(self):
        """Una transacción pendiente en la que la dirección es receptora aparece en el historial."""
        pending = [
            {
                "_id": "id-002",
                "from": "other_wallet",
                "to": self.TARGET_ADDRESS,
                "amount": 75.0,
                "timestamp": "2026-06-01T11:00:00Z",
                "status": "PENDING",
            }
        ]
        result = self._call(pending_txs=pending, blocks=[])
        assert len(result) == 1
        assert result[0]["to"] == self.TARGET_ADDRESS

    def test_confirmed_tx_in_block_appears_with_confirmed_status(self):
        """Una transacción confirmada en un bloque aparece con status=CONFIRMED."""
        block = {
            "index": 3,
            "transactions": [
                {
                    "id": "tx-block-001",
                    "from": self.TARGET_ADDRESS,
                    "to": "other_wallet",
                    "amount": 100.0,
                    "timestamp": "2026-06-02T10:00:00Z",
                }
            ],
        }
        result = self._call(pending_txs=[], blocks=[block])
        assert len(result) == 1
        assert result[0]["status"] == "CONFIRMED"

    def test_confirmed_tx_has_block_index(self):
        """Una transacción confirmada debe incluir el block_index del bloque contenedor."""
        block = {
            "index": 5,
            "transactions": [
                {
                    "id": "tx-block-002",
                    "from": "other_wallet",
                    "to": self.TARGET_ADDRESS,
                    "amount": 200.0,
                    "timestamp": "2026-06-02T11:00:00Z",
                }
            ],
        }
        result = self._call(pending_txs=[], blocks=[block])
        assert result[0]["block_index"] == 5

    def test_tx_in_block_unrelated_to_address_is_excluded(self):
        """Las transacciones en un bloque que no involucren la dirección no aparecen."""
        block = {
            "index": 1,
            "transactions": [
                {
                    "id": "tx-unrelated",
                    "from": "wallet_x",
                    "to": "wallet_y",
                    "amount": 999.0,
                    "timestamp": "2026-06-01T09:00:00Z",
                }
            ],
        }
        result = self._call(pending_txs=[], blocks=[block])
        assert result == []

    def test_results_sorted_by_timestamp_descending(self):
        """Los resultados deben estar ordenados del más reciente al más antiguo."""
        pending = [
            {
                "_id": "id-early",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 10.0,
                "timestamp": "2026-06-01T08:00:00Z",
                "status": "PENDING",
            },
            {
                "_id": "id-late",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 20.0,
                "timestamp": "2026-06-03T15:00:00Z",
                "status": "PENDING",
            },
        ]
        result = self._call(pending_txs=pending, blocks=[])
        assert result[0]["timestamp"] > result[1]["timestamp"]

    def test_pagination_page1_limit2(self):
        """page=1, limit=2 devuelve solo los 2 primeros (más recientes)."""
        pending = [
            {
                "_id": f"id-{i}",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": float(i),
                "timestamp": f"2026-06-0{i}T10:00:00Z",
                "status": "PENDING",
            }
            for i in range(1, 5)  # 4 transacciones
        ]
        result = self._call(pending_txs=pending, blocks=[], page=1, limit=2)
        assert len(result) == 2

    def test_pagination_page2_limit2(self):
        """page=2, limit=2 devuelve los 2 siguientes."""
        pending = [
            {
                "_id": f"id-{i}",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": float(i),
                "timestamp": f"2026-06-0{i}T10:00:00Z",
                "status": "PENDING",
            }
            for i in range(1, 5)  # 4 transacciones
        ]
        result_p1 = self._call(pending_txs=pending, blocks=[], page=1, limit=2)
        # Reiniciar iterador (patch se descarta al salir del contexto)
        result_p2 = self._call(pending_txs=pending, blocks=[], page=2, limit=2)

        assert len(result_p2) == 2
        # Las páginas no deben tener elementos en común (usando timestamp como proxy)
        timestamps_p1 = {r["timestamp"] for r in result_p1}
        timestamps_p2 = {r["timestamp"] for r in result_p2}
        assert timestamps_p1.isdisjoint(timestamps_p2)

    def test_page_beyond_results_returns_empty(self):
        """Una página fuera del rango de resultados retorna lista vacía."""
        pending = [
            {
                "_id": "id-1",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 10.0,
                "timestamp": "2026-06-01T10:00:00Z",
                "status": "PENDING",
            }
        ]
        result = self._call(pending_txs=pending, blocks=[], page=99, limit=10)
        assert result == []

    def test_tx_without_timestamp_does_not_break_sort(self):
        """Una transacción sin timestamp no debe romper el ordenamiento (usa '' como fallback)."""
        pending = [
            {
                "_id": "id-no-ts",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 5.0,
                "status": "PENDING",
                # sin timestamp
            },
            {
                "_id": "id-with-ts",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 10.0,
                "timestamp": "2026-06-01T10:00:00Z",
                "status": "PENDING",
            },
        ]
        # No debe lanzar excepción
        result = self._call(pending_txs=pending, blocks=[])
        assert len(result) == 2

    def test_pending_tx_without_explicit_status_defaults_to_pending(self):
        """Una transacción del mempool sin campo status recibe status=PENDING."""
        pending = [
            {
                "_id": "id-no-status",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 15.0,
                "timestamp": "2026-06-01T12:00:00Z",
                # sin status
            }
        ]
        result = self._call(pending_txs=pending, blocks=[])
        assert result[0]["status"] == "PENDING"

    def test_id_converted_to_string(self):
        """El campo _id de MongoDB se convierte a string en el resultado."""
        from bson import ObjectId

        object_id = ObjectId()
        pending = [
            {
                "_id": object_id,
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 5.0,
                "timestamp": "2026-06-01T10:00:00Z",
                "status": "PENDING",
            }
        ]
        result = self._call(pending_txs=pending, blocks=[])
        assert result[0]["_id"] == str(object_id)

    def test_combined_pending_and_confirmed_transactions(self):
        """El historial combina transacciones pendientes y confirmadas en bloques."""
        pending = [
            {
                "_id": "pend-001",
                "from": self.TARGET_ADDRESS,
                "to": "other",
                "amount": 10.0,
                "timestamp": "2026-06-03T10:00:00Z",
                "status": "PENDING",
            }
        ]
        block = {
            "index": 2,
            "transactions": [
                {
                    "id": "block-tx-001",
                    "from": "other",
                    "to": self.TARGET_ADDRESS,
                    "amount": 50.0,
                    "timestamp": "2026-06-01T10:00:00Z",
                }
            ],
        }
        result = self._call(pending_txs=pending, blocks=[block])
        assert len(result) == 2

        statuses = {r["status"] for r in result}
        assert "PENDING" in statuses
        assert "CONFIRMED" in statuses
