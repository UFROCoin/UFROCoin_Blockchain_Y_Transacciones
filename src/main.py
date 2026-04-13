from fastapi import FastAPI

from src.api.global_router import router as global_router
from src.api.startup import lifespan


app = FastAPI(
    title="UFROCoin Blockchain Core",
    lifespan=lifespan,
)

app.include_router(global_router)
