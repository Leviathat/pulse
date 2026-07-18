"""Stage-0 stub: health endpoint only. Real endpoints arrive in stages 1-2."""

from fastapi import FastAPI

app = FastAPI(title="Pulse API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
