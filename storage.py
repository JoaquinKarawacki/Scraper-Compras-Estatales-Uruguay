"""
storage.py
----------
Manejo de historial de publicaciones ya notificadas.
Soporta SQLite (por defecto) o JSON como alternativa simple.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import config
from utils import parse_deadline

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
            conn.execute("PRAGMA journal_mode=WAL")
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


# ---------------------------------------------------------------------------
# Panel web — licitaciones activas / solicitadas / archivadas
#
# Tabla independiente de `seen_publications`: esta última sigue existiendo
# solo para deduplicar el envío de emails. `licitaciones` guarda TODAS las
# publicaciones relevantes que el scraper va encontrando (nuevas o no) para
# que el panel web siempre pueda mostrarlas, con un estado manual separado
# (`estado_manual`) que el usuario controla desde la interfaz.
# ---------------------------------------------------------------------------

ESTADOS_MANUALES = ("ninguno", "solicitada", "archivada")


class LicitacionesStore:
    """Almacena todas las licitaciones relevantes encontradas, para el panel web."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS licitaciones (
                    pub_id           TEXT PRIMARY KEY,
                    source           TEXT NOT NULL DEFAULT 'comprasestatales',
                    title            TEXT,
                    organism         TEXT,
                    description      TEXT,
                    url              TEXT,
                    date_raw         TEXT,
                    deadline_at      TEXT,
                    matched_keywords TEXT,
                    first_seen       TEXT NOT NULL,
                    last_seen        TEXT NOT NULL,
                    estado_manual    TEXT NOT NULL DEFAULT 'ninguno'
                                     CHECK (estado_manual IN ('ninguno','solicitada','archivada')),
                    estado_manual_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_licitaciones_activas
                ON licitaciones(estado_manual, deadline_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_licitaciones_estado
                ON licitaciones(estado_manual, estado_manual_at)
            """)
            conn.commit()

    def upsert_batch(self, items: list[dict]):
        """Inserta o refresca licitaciones relevantes. Nunca toca estado_manual."""
        if not items:
            return
        now = datetime.utcnow().isoformat()
        rows = []
        for it in items:
            deadline = parse_deadline(it.get("date", ""))
            rows.append((
                it["id"],
                it.get("title", ""),
                it.get("organism", ""),
                it.get("description", ""),
                it.get("url", ""),
                it.get("date", ""),
                deadline.isoformat() if deadline else None,
                json.dumps(it.get("matched_keywords", []), ensure_ascii=False),
                now,
                now,
            ))
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO licitaciones
                    (pub_id, title, organism, description, url, date_raw,
                     deadline_at, matched_keywords, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pub_id) DO UPDATE SET
                    title            = excluded.title,
                    organism         = excluded.organism,
                    description      = excluded.description,
                    url              = excluded.url,
                    date_raw         = excluded.date_raw,
                    deadline_at      = excluded.deadline_at,
                    matched_keywords = excluded.matched_keywords,
                    last_seen        = excluded.last_seen
                """,
                rows
            )
            conn.commit()

    def list_activas(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute(
                """
                SELECT COUNT(*) FROM licitaciones
                WHERE estado_manual = 'ninguno'
                  AND (deadline_at IS NULL OR deadline_at >= ?)
                """,
                (datetime.now().isoformat(),)
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM licitaciones
                WHERE estado_manual = 'ninguno'
                  AND (deadline_at IS NULL OR deadline_at >= ?)
                ORDER BY (deadline_at IS NULL) ASC, deadline_at ASC
                LIMIT ? OFFSET ?
                """,
                (datetime.now().isoformat(), limit, offset)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows], total

    def list_by_estado(self, estado: str, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute(
                "SELECT COUNT(*) FROM licitaciones WHERE estado_manual = ?", (estado,)
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM licitaciones
                WHERE estado_manual = ?
                ORDER BY estado_manual_at DESC
                LIMIT ? OFFSET ?
                """,
                (estado, limit, offset)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows], total

    def set_estado(self, pub_id: str, nuevo_estado: str) -> str:
        """
        Cambia el estado manual de una licitación (solicitar/archivar).
        Retorna: 'ok', 'not_found' o 'conflict' (ya tenía un estado manual asignado).
        """
        if nuevo_estado not in ("solicitada", "archivada"):
            raise ValueError(f"Estado inválido: {nuevo_estado}")
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT estado_manual FROM licitaciones WHERE pub_id = ?", (pub_id,)
            ).fetchone()
            if row is None:
                return "not_found"
            if row[0] != "ninguno":
                return "conflict"
            conn.execute(
                "UPDATE licitaciones SET estado_manual = ?, estado_manual_at = ? WHERE pub_id = ?",
                (nuevo_estado, now, pub_id)
            )
            conn.commit()
            return "ok"

    def stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            now_iso = datetime.now().isoformat()
            total_activas = conn.execute(
                """
                SELECT COUNT(*) FROM licitaciones
                WHERE estado_manual = 'ninguno'
                  AND (deadline_at IS NULL OR deadline_at >= ?)
                """,
                (now_iso,)
            ).fetchone()[0]
            total_solicitadas = conn.execute(
                "SELECT COUNT(*) FROM licitaciones WHERE estado_manual = 'solicitada'"
            ).fetchone()[0]
            total_archivadas = conn.execute(
                "SELECT COUNT(*) FROM licitaciones WHERE estado_manual = 'archivada'"
            ).fetchone()[0]
            en_7_dias = (datetime.now().replace(microsecond=0) + timedelta(days=7)).isoformat()
            vencen_pronto = conn.execute(
                """
                SELECT COUNT(*) FROM licitaciones
                WHERE estado_manual = 'ninguno'
                  AND deadline_at IS NOT NULL
                  AND deadline_at >= ? AND deadline_at <= ?
                """,
                (now_iso, en_7_dias)
            ).fetchone()[0]
        return {
            "total_activas": total_activas,
            "total_solicitadas": total_solicitadas,
            "total_archivadas": total_archivadas,
            "vencen_pronto": vencen_pronto,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["matched_keywords"] = json.loads(d.get("matched_keywords") or "[]")
        except json.JSONDecodeError:
            d["matched_keywords"] = []
        deadline_at = d.get("deadline_at")
        if deadline_at:
            dias_restantes = (datetime.fromisoformat(deadline_at) - datetime.now()).days
            d["dias_restantes"] = dias_restantes
        else:
            d["dias_restantes"] = None
        return d


def upsert_relevant_licitaciones(items: list[dict]):
    """Refresca la tabla `licitaciones` del panel web con todas las relevantes de esta corrida."""
    if not items:
        return
    store = LicitacionesStore(config.DB_PATH)
    store.upsert_batch(items)
    logger.info(f"Panel: {len(items)} licitaciones relevantes actualizadas en 'licitaciones'.")
