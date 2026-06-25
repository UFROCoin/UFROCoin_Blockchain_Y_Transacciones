"""Consumer del evento wallet.credit.issued (contrato cross-módulo).

Refleja el crédito inicial de 100 coins que emite el módulo de Usuarios cuando
se registra una wallet. El crédito se persiste como una transacción CONFIRMED
off-chain (block_index None) en la colección transactions del blockchain, de modo
que calculate_balance lo sume al saldo. La idempotencia se garantiza por credit_id
(un crédito por usuario), así un redelivery de RabbitMQ nunca duplica el saldo.

El consumer corre in-process: se lanza como task del lifespan de la API
(ver src/api/startup.py) sobre el mismo event loop de uvicorn vía aio-pika.
No necesita proceso ni contenedor aparte.
"""

import asyncio
import json
import logging
import os
from functools import partial

from src.core.constants import (
    BLOCKCHAIN_EVENTS_EXCHANGE,
    WALLET_CREDIT_QUEUE,
    WALLET_CREDIT_ROUTING_KEY,
)
from src.core.database import get_transactions_collection

LOGGER = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@localhost:5672/%2F"
RECONNECT_DELAY_SECONDS = 5


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


async def _handle_message(transactions_collection, message) -> None:
    """Procesa un mensaje aio-pika: ack al persistir, nack (sin requeue) si falla.

    process_credit_event usa pymongo síncrono. El upsert es local y de bajo
    volumen (uno por registro), así que bloquear el loop ese instante es
    aceptable.
    ponytail: upsert sync en el event loop; envolver en run_in_executor si el
    volumen de créditos creciera.
    """
    try:
        process_credit_event(transactions_collection, message.body)
        await message.ack()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("No se pudo procesar wallet.credit.issued: %s", exc)
        await message.nack(requeue=False)


def _rabbitmq_url() -> str:
    return os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)


async def start_wallet_credit_consumer() -> None:
    """Loop resiliente del consumer. Pensado para asyncio.create_task en lifespan.

    Reintenta la conexión si RabbitMQ no está disponible, de modo que la API
    arranca igual aunque el broker tarde o se caiga. Se detiene limpiamente al
    cancelar la task.
    """
    import aio_pika

    transactions_collection = get_transactions_collection()
    ensure_indexes(transactions_collection)

    while True:
        try:
            connection = await aio_pika.connect_robust(_rabbitmq_url())
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=1)
                exchange = await channel.declare_exchange(
                    BLOCKCHAIN_EVENTS_EXCHANGE,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                queue = await channel.declare_queue(WALLET_CREDIT_QUEUE, durable=True)
                await queue.bind(exchange, routing_key=WALLET_CREDIT_ROUTING_KEY)
                await queue.consume(partial(_handle_message, transactions_collection))

                LOGGER.info("Escuchando eventos %s...", WALLET_CREDIT_ROUTING_KEY)
                await asyncio.Future()  # corre hasta que la task se cancele
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Consumer wallet.credit.issued caido, reintento en %ss: %s",
                RECONNECT_DELAY_SECONDS,
                exc,
            )
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
