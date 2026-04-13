from fastapi import FastAPI

from src.api.startup import lifespan


app = FastAPI(
    title="UFROCoin Blockchain Core",
    lifespan=lifespan,
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
