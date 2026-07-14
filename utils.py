"""
utils.py
--------
Funciones utilitarias sin dependencias internas.
Separado para evitar importaciones circulares.
"""

import re
from datetime import datetime
from typing import Optional


ACCENT_MAP = str.maketrans(
    "áéíóúàèìòùäëïöüÁÉÍÓÚÀÈÌÒÙÄËÏÖÜ",
    "aeiouaeiouaeiouAEIOUAEIOUAEIOU"
)


def normalize(text: str) -> str:
    """Quita tildes y pone en minúsculas para comparación."""
    return text.translate(ACCENT_MAP).lower()


_DEADLINE_RE = re.compile(
    r'(\d{1,2})/(\d{1,2})/(\d{4})(?:\D+(\d{1,2}):(\d{2}))?'
)


def parse_deadline(date_raw: str) -> Optional[datetime]:
    """
    Extrae la fecha límite de un texto libre tipo:
      "Recepción hasta: 15/04/2026 10:00hs"
      "Recepción de ofertas hasta: 15/04/2026"
    Formato esperado: dd/mm/yyyy, hora opcional HH:MM.
    Si no hay hora, asume 23:59 (fin del día) para no marcar como vencida
    una licitación que en realidad sigue vigente todo ese día.
    Retorna None si no se pudo parsear (nunca lanza excepción).
    """
    if not date_raw:
        return None
    m = _DEADLINE_RE.search(date_raw)
    if not m:
        return None
    day, month, year, hh, mm = m.groups()
    try:
        hour = int(hh) if hh else 23
        minute = int(mm) if mm else 59
        return datetime(int(year), int(month), int(day), hour, minute)
    except ValueError:
        return None


def is_active(deadline_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """
    Determina si una licitación sigue vigente según su fecha límite.
    Fallback: si no se pudo parsear la fecha, se considera ACTIVA
    (mejor mostrar de más que perder silenciosamente una oportunidad real).
    """
    if deadline_at is None:
        return True
    now = now or datetime.now()
    return deadline_at >= now
