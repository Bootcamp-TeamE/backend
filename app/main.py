from fastapi import FastAPI

app = FastAPI(title="마감할인 API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
