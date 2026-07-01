"""Consumer del evento block.mined (M3 -> M2).

Persiste cada bloque minado en la coleccion blocks del M2, convirtiendo el
evento del bus en el registro oficial de la cadena. La idempotencia se
garantiza por hash: un redelivery de RabbitMQ nunca duplica un bloque.

El consumer corre in-process como task del lifespan de la API.
"""

import asyncio
import json
import logging
import os
from functools import partial

from bson import ObjectId

from src.core.constants import (
    BLOCK_MINED_QUEUE,
    BLOCK_MINED_ROUTING_KEY,
    MINING_EVENTS_EXCHANGE,
)
from src.core.database import get_blocks_collection, get_transactions_collection

LOGGER = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@localhost:5672/%2F"
RECONNECT_DELAY_SECONDS = 5


def persist_block(blocks_collection, block: dict) -> None:
    """Inserta el bloque de forma idempotente por hash."""
    blocks_collection.update_one(
        {"hash": block["hash"]},
        {"$setOnInsert": block},
        upsert=True,
    )


def confirm_block_transactions(transactions_collection, block: dict) -> None:
    """Marca como confirmadas las transacciones locales incluidas en el bloque."""
    block_index = block.get("index")

    for transaction in block.get("transactions", []):
        transaction_id = transaction.get("transaction_id") or transaction.get("id")
        if not transaction_id:
            continue

        mongo_id = (
            ObjectId(str(transaction_id))
            if ObjectId.is_valid(str(transaction_id))
            else transaction_id
        )
        transactions_collection.update_one(
            {"_id": mongo_id},
            {"$set": {"status": "CONFIRMED", "block_index": block_index}},
        )


def process_block_mined_event(
    blocks_collection,
    body,
    transactions_collection=None,
) -> None:
    """Decodifica el envelope block.mined y persiste el bloque."""
    event = json.loads(body)
    block = event["data"]
    persist_block(blocks_collection, block)
    if transactions_collection is not None:
        confirm_block_transactions(transactions_collection, block)
    LOGGER.info(
        "Bloque index=%s hash=%s persistido desde block.mined",
        block.get("index"),
        block.get("hash", "")[:16],
    )


def ensure_indexes(blocks_collection) -> None:
    """Indice unico sobre hash para blindar la idempotencia a nivel de DB."""
    blocks_collection.create_index(
        "hash",
        unique=True,
        name="blocks_hash_unique",
    )


async def _handle_message(blocks_collection, message, transactions_collection=None) -> None:
    """Procesa un mensaje aio-pika: ack al persistir, nack si falla."""
    try:
        process_block_mined_event(
            blocks_collection,
            message.body,
            transactions_collection,
        )
        await message.ack()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("No se pudo procesar block.mined: %s", exc)
        await message.nack(requeue=False)


def _rabbitmq_url() -> str:
    return os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)


async def start_block_mined_consumer() -> None:
    """Loop resiliente del consumer. Pensado para asyncio.create_task."""
    import aio_pika

    blocks_collection = get_blocks_collection()
    transactions_collection = get_transactions_collection()
    ensure_indexes(blocks_collection)

    while True:
        try:
            connection = await aio_pika.connect_robust(_rabbitmq_url())
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=1)
                exchange = await channel.declare_exchange(
                    MINING_EVENTS_EXCHANGE,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                queue = await channel.declare_queue(BLOCK_MINED_QUEUE, durable=True)
                await queue.bind(exchange, routing_key=BLOCK_MINED_ROUTING_KEY)
                await queue.consume(
                    partial(
                        _handle_message,
                        blocks_collection,
                        transactions_collection=transactions_collection,
                    )
                )

                LOGGER.info("Escuchando eventos %s...", BLOCK_MINED_ROUTING_KEY)
                await asyncio.Future()  # corre hasta que la task se cancele
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Consumer block.mined caido, reintento en %ss: %s",
                RECONNECT_DELAY_SECONDS,
                exc,
            )
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
