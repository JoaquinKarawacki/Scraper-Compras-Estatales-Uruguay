"""
api.py
------
Panel web (FastAPI) para revisar licitaciones activas y marcarlas
manualmente como "solicitada" o "archivada".

Corre como servicio separado del cron del scraper, sobre la misma
base SQLite (config.DB_PATH). Es de solo lectura + cambio de estado
manual: no scrapea ni envía mail (eso lo sigue haciendo main.py).

Uso local:
    uvicorn api:app --reload --port 8010

En Railway: segundo servicio en el mismo proyecto/repo, sin Cron
Schedule (siempre encendido), Start Command:
    uvicorn api:app --host 0.0.0.0 --port $PORT
compartiendo el mismo Volume (y el mismo DB_PATH) que el servicio
del scraper — ver README.md, sección "Panel web en Railway".
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import config
from storage import LicitacionesStore

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"

app = FastAPI(title="Panel de Licitaciones - Compras Estatales Uruguay")


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
