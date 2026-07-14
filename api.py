"""
api.py
------
Servicio único: panel web (FastAPI) + scraping periódico en el mismo proceso.

Un scheduler interno (APScheduler) dispara `main.run_once()` cada
`config.SCRAPE_INTERVAL_HOURS` horas, en un hilo aparte para no bloquear
el servidor. El panel lee/escribe la misma base SQLite (config.DB_PATH)
que ese ciclo va llenando — todo en un solo proceso, un solo volume.

Uso local:
    uvicorn api:app --reload --port 8010

En Railway: un único servicio, siempre encendido (sin Cron Schedule),
Start Command:
    uvicorn api:app --host 0.0.0.0 --port $PORT
usando el mismo Volume/DB_PATH que ya tenía el scraper — ver README.md,
sección "Panel web en Railway".
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import config
from storage import LicitacionesStore
from main import run_once, setup_logging

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"

logger = logging.getLogger("api")
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    scheduler.add_job(
        run_once,
        "interval",
        hours=config.SCRAPE_INTERVAL_HOURS,
        id="scrape_cycle",
        max_instances=1,  # nunca dos scrapings en paralelo si uno tarda más que el intervalo
    )
    scheduler.start()
    logger.info(f"Scheduler iniciado: scraping cada {config.SCRAPE_INTERVAL_HOURS}h.")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Panel de Licitaciones - Compras Estatales Uruguay", lifespan=lifespan)


def get_store() -> LicitacionesStore:
    return LicitacionesStore(config.DB_PATH)


@app.get("/api/activas")
def api_activas(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = get_store().list_activas(limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/solicitadas")
def api_solicitadas(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = get_store().list_by_estado("solicitada", limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/archivadas")
def api_archivadas(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = get_store().list_by_estado("archivada", limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/stats")
def api_stats():
    return get_store().stats()


@app.post("/api/licitaciones/{pub_id}/solicitar")
def api_solicitar(pub_id: str):
    return _cambiar_estado(pub_id, "solicitada")


@app.post("/api/licitaciones/{pub_id}/archivar")
def api_archivar(pub_id: str):
    return _cambiar_estado(pub_id, "archivada")


def _cambiar_estado(pub_id: str, nuevo_estado: str):
    resultado = get_store().set_estado(pub_id, nuevo_estado)
    if resultado == "not_found":
        raise HTTPException(status_code=404, detail="Licitación no encontrada")
    if resultado == "conflict":
        raise HTTPException(status_code=409, detail="La licitación ya tiene un estado asignado")
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
