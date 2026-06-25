"""Consumer del evento wallet.credit.issued (contrato cross-módulo).

Refleja el crédito inicial de 100 coins que emite el módulo de Usuarios cuando
se registra una wallet. El crédito se persiste como una transacción CONFIRMED
off-chain (block_index None) en la colección transactions del blockchain, de modo
que calculate_balance lo sume al saldo. La idempotencia se garantiza por credit_id
(un crédito por usuario), así un redelivery de RabbitMQ nunca duplica el saldo.
"""

import json
import logging
import os

from src.core.constants import (
    BLOCKCHAIN_EVENTS_EXCHANGE,
    WALLET_CREDIT_QUEUE,
    WALLET_CREDIT_ROUTING_KEY,
)
from src.core.database import get_transactions_collection

LOGGER = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@localhost:5672/%2F"


def build_credit_document(data: dict) -> dict:
    """Mapea el payload del contrato a un documento de transacción off-chain."""
    return {
        "from": data["from"],
        "to": data["to"],
        "amount": data["amount"],
        "type": data.get("type", "GENESIS"),
        "status": "CONFIRMED",
        "block_index": None,            # emisión confirmada off-chain, nunca minada
        "credit_id": data["credit_id"],  # clave de idempotencia (1 crédito por usuario)
        "timestamp": data["timestamp"],
    }


def persist_credit(transactions_collection, data: dict) -> None:
    """Inserta el crédito de forma idempotente por credit_id."""
    transactions_collection.update_one(
        {"credit_id": data["credit_id"]},
        {"$setOnInsert": build_credit_document(data)},
        upsert=True,
    )


def process_credit_event(transactions_collection, body) -> None:
    """Decodifica el envelope del evento y persiste el crédito."""
    event = json.loads(body)
    data = event["data"]
    persist_credit(transactions_collection, data)
    LOGGER.info(
        "Credito wallet.credit.issued aplicado a %s (credit_id=%s)",
        data.get("to"),
        data.get("credit_id"),
    )


def ensure_indexes(transactions_collection) -> None:
    """Índice único sobre credit_id para blindar la idempotencia a nivel de DB."""
    transactions_collection.create_index(
        "credit_id",
        unique=True,
        sparse=True,  # solo indexa documentos que tengan credit_id (no las transferencias)
        name="transactions_credit_id_unique",
    )


def _build_callback(transactions_collection):
    def callback(ch, method, properties, body):
        try:
            process_credit_event(transactions_collection, body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudo procesar wallet.credit.issued: %s", exc)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    return callback


def start_genesis_credit_worker() -> None:
    import pika

    transactions_collection = get_transactions_collection()
    ensure_indexes(transactions_collection)

    parameters = pika.URLParameters(os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL))
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(
        exchange=BLOCKCHAIN_EVENTS_EXCHANGE,
        exchange_type="topic",
        durable=True,
    )
    channel.queue_declare(queue=WALLET_CREDIT_QUEUE, durable=True)
    channel.queue_bind(
        exchange=BLOCKCHAIN_EVENTS_EXCHANGE,
        queue=WALLET_CREDIT_QUEUE,
        routing_key=WALLET_CREDIT_ROUTING_KEY,
    )

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=WALLET_CREDIT_QUEUE,
        on_message_callback=_build_callback(transactions_collection),
    )

    LOGGER.info("Esperando eventos %s...", WALLET_CREDIT_ROUTING_KEY)
    channel.start_consuming()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_genesis_credit_worker()
