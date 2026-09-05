from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import accounts, actions, plays, reports, signals

app = FastAPI(title="Polst CS Agent Platform")

# Local-dev only: the console (Next.js, localhost:3000) calls this API
# (localhost:8000) cross-origin. Tighten this before anything but
# synthetic data flows through it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(signals.router)
app.include_router(actions.router)
app.include_router(reports.router)
app.include_router(plays.router)


@app.get("/")
def root() -> dict:
    return {"message": "Polst CS Agent Platform"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
