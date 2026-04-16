from fastapi import FastAPI
feature/valid-block-structure
from src.api.block_router import router as block_router
from src.core.database import close_db_client

app = FastAPI(
    title="UFROCoin Module 2 API",
    description="Blockchain and transactions service for UFROCoin.",
    version="1.0.0",
)

app.include_router(block_router, prefix="/api")


@app.on_event("shutdown")
def shutdown_event() -> None:
    close_db_client()