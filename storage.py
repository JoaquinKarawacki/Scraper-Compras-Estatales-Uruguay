"""
storage.py
----------
Manejo de historial de publicaciones ya notificadas.
Soporta SQLite (por defecto) o JSON como alternativa simple.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLite (recomendado)
# ---------------------------------------------------------------------------

class SQLiteStorage:
    """Almacena publicaciones ya notificadas en SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_publications (
                    pub_id      TEXT PRIMARY KEY,
                    url         TEXT,
                    title       TEXT,
                    organism    TEXT,
                    first_seen  TEXT NOT NULL,
                    notified_at TEXT NOT NULL
                )
            """)
            # Índice para búsquedas rápidas
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pub_id
                ON seen_publications(pub_id)
            """)
            conn.commit()

    def is_seen(self, pub_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_publications WHERE pub_id = ?", (pub_id,)
            ).fetchone()
            return row is not None

    def mark_seen(self, item: dict):
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_publications
                    (pub_id, url, title, organism, first_seen, notified_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item.get("url", ""),
                    item.get("title", "")[:500],
                    item.get("organism", "")[:200],
                    now,
                    now,
                )
            )
            conn.commit()

    def mark_seen_batch(self, items: list[dict]):
        now = datetime.utcnow().isoformat()
        rows = [
            (
                it["id"],
                it.get("url", ""),
                it.get("title", "")[:500],
                it.get("organism", "")[:200],
                now,
                now,
            )
            for it in items
        ]
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO seen_publications
                    (pub_id, url, title, organism, first_seen, notified_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows
            )
            conn.commit()

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM seen_publications").fetchone()[0]

    def cleanup_old(self, days: int = 180):
        """Elimina registros más viejos que N días para no crecer indefinidamente."""
        cutoff = datetime.utcnow().replace(microsecond=0)
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                "DELETE FROM seen_publications WHERE first_seen < date('now', ?)",
                (f"-{days} days",)
            ).rowcount
            conn.commit()
        if deleted:
            logger.info(f"Storage: {deleted} registros antiguos eliminados.")


# ---------------------------------------------------------------------------
# JSON (alternativa simple)
# ---------------------------------------------------------------------------

class JSONStorage:
    """Almacena IDs de publicaciones en un archivo JSON."""

    def __init__(self, json_path: str):
        self.json_path = Path(json_path)
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.json_path.exists():
            try:
                with open(self.json_path) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Archivo JSON de historial corrupto, reiniciando.")
        return {"seen_ids": {}}

    def _save(self):
        with open(self.json_path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def is_seen(self, pub_id: str) -> bool:
        return pub_id in self._data.get("seen_ids", {})

    def mark_seen(self, item: dict):
        self._data.setdefault("seen_ids", {})[item["id"]] = {
            "url": item.get("url", ""),
            "title": item.get("title", "")[:200],
            "notified_at": datetime.utcnow().isoformat(),
        }
        self._save()

    def mark_seen_batch(self, items: list[dict]):
        now = datetime.utcnow().isoformat()
        seen = self._data.setdefault("seen_ids", {})
        for it in items:
            seen[it["id"]] = {
                "url": it.get("url", ""),
                "title": it.get("title", "")[:200],
                "notified_at": now,
            }
        self._save()

    def count(self) -> int:
        return len(self._data.get("seen_ids", {}))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage():
    """Retorna la implementación de storage configurada."""
    if config.USE_SQLITE:
        logger.debug(f"Usando SQLite: {config.DB_PATH}")
        return SQLiteStorage(config.DB_PATH)
    else:
        logger.debug(f"Usando JSON: {config.HISTORY_JSON_PATH}")
        return JSONStorage(config.HISTORY_JSON_PATH)


def filter_new_publications(items: list[dict]) -> list[dict]:
    """
    Filtra la lista de publicaciones, devolviendo solo las que
    no han sido notificadas antes.
    """
    storage = get_storage()
    new_items = [it for it in items if not storage.is_seen(it["id"])]
    logger.info(
        f"Storage: {len(items)} relevantes, "
        f"{len(items) - len(new_items)} ya notificadas, "
        f"{len(new_items)} nuevas."
    )
    return new_items


def mark_as_notified(items: list[dict]):
    """Marca una lista de publicaciones como notificadas."""
    if not items:
        return
    storage = get_storage()
    storage.mark_seen_batch(items)
    logger.info(f"Storage: {len(items)} publicaciones marcadas como notificadas.")
