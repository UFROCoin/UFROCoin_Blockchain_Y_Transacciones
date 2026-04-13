import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.database import close_database, initialize_database
from src.core.rabbitmq import close_rabbitmq_connection
from src.services.genesis_service import GenesisService

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    genesis_service = GenesisService()
    created_block = genesis_service.create_genesis_if_needed()
    if created_block is not None:
        LOGGER.info("Genesis block creado con hash %s", created_block["hash"])

    try:
        yield
    finally:
        close_rabbitmq_connection()
        close_database()
