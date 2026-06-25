import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from src.core.database import close_database, initialize_database
from src.core.rabbitmq_publisher import close_rabbitmq_connection
from src.services.genesis_service import GenesisService
from src.workers.genesis_credit_consumer import start_wallet_credit_consumer

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    genesis_service = GenesisService()
    created_block = genesis_service.create_genesis_if_needed()
    if created_block is not None:
        LOGGER.info("Genesis block creado con hash %s", created_block["hash"])

    # Consumer in-process de wallet.credit.issued: la propia API escucha el bus.
    consumer_task = asyncio.create_task(start_wallet_credit_consumer())

    try:
        yield
    finally:
        consumer_task.cancel()
        with suppress(asyncio.CancelledError):
            await consumer_task
        close_rabbitmq_connection()
        close_database()
