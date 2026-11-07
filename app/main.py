from fastapi import FastAPI

app = FastAPI(title="Emalert")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "emalert"}
