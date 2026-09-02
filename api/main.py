from fastapi import FastAPI

app = FastAPI(title="Polst CS Agent Platform")


@app.get("/")
def root() -> dict:
    return {"message": "Polst CS Agent Platform"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
