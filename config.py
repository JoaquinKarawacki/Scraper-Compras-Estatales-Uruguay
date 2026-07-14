"""
config.py
---------
Configuración centralizada. Carga desde variables de entorno (.env).
"""
 
import os
from pathlib import Path
from dotenv import load_dotenv
 
# Cargar .env desde el directorio del proyecto
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
 
 
def _get_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes", "on")
 
 
def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default
 
 
class Config:
    # --- URLs ---
    SITE_BASE: str = os.getenv("SITE_BASE", "https://www.comprasestatales.gub.uy")
    BASE_URL: str = os.getenv(
        "BASE_URL",
        "https://www.comprasestatales.gub.uy/consultas/?tipo-pub=ADJ&reset=1"
    )
 
    # --- Filtros de contenido ---
    HEADER_TYPES: list[str] = [
        t.strip()
        for t in os.getenv("HEADER_TYPES", "Licitación,Compra Directa").split(",")
        if t.strip()
    ]
    HEADER_TYPES_NORMALIZED: list[str] = []  # Se llena en __post_init__
 
    BODY_KEYWORDS: list[str] = [
        k.strip()
        for k in os.getenv(
            "BODY_KEYWORDS",
            "consultoría,eficiencia energética,iluminacion,iluminación,"
            "luminarias,ambiental,mantenimiento,trafos"
        ).split(",")
        if k.strip()
    ]
 
    # --- Email (Microsoft Graph API) ---
    MS_TENANT_ID: str = os.getenv("MS_TENANT_ID", "")
    MS_CLIENT_ID: str = os.getenv("MS_CLIENT_ID", "")
    MS_CLIENT_SECRET: str = os.getenv("MS_CLIENT_SECRET", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_TO: str = os.getenv("EMAIL_TO", "")
    EMAIL_SUBJECT: str = os.getenv(
        "EMAIL_SUBJECT",
        "Nuevas oportunidades detectadas - Compras Estatales"
    )
    SEND_IF_EMPTY: bool = _get_bool("SEND_IF_EMPTY", False)
 
    # --- Base de datos / deduplicación ---
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "seen_publications.db"))
    HISTORY_JSON_PATH: str = os.getenv(
        "HISTORY_JSON_PATH",
        str(BASE_DIR / "data" / "seen_ids.json")
    )
    USE_SQLITE: bool = _get_bool("USE_SQLITE", True)
 
    # --- Scraping ---
    USE_PLAYWRIGHT: bool = _get_bool("USE_PLAYWRIGHT", True)
    MAX_PAGES: int = _get_int("MAX_PAGES", 10)
    PAGE_TIMEOUT_MS: int = _get_int("PAGE_TIMEOUT_MS", 30000)
    REQUEST_TIMEOUT: int = _get_int("REQUEST_TIMEOUT", 30)
    MAX_RETRIES: int = _get_int("MAX_RETRIES", 3)
    RETRY_DELAY: int = _get_int("RETRY_DELAY", 5)
 
    # --- Selectores CSS (ajustar según HTML real del sitio) ---
    RESULTS_SELECTOR: str = os.getenv("RESULTS_SELECTOR", "table tbody tr, div.resultado-item")
    NEXT_PAGE_SELECTOR: str = os.getenv("NEXT_PAGE_SELECTOR", "a.siguiente, li.next a, [aria-label='siguiente']")
    NEXT_PAGE_SELECTOR_BS: str = os.getenv("NEXT_PAGE_SELECTOR_BS", "a.siguiente, li.next a")
 
    # --- Scheduler interno del panel web (api.py) ---
    # Expresión cron estándar (min hora día mes día-semana). Default: todos los días a las 8:00.
    SCRAPE_CRON: str = os.getenv("SCRAPE_CRON", "0 8 * * *")
    SCRAPE_TIMEZONE: str = os.getenv("SCRAPE_TIMEZONE", "America/Montevideo")

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "scraper.log"))
    LOG_MAX_BYTES: int = _get_int("LOG_MAX_BYTES", 5_000_000)   # 5 MB
    LOG_BACKUP_COUNT: int = _get_int("LOG_BACKUP_COUNT", 5)
 
    def __init__(self):
        # Normalizar tipos de encabezado para comparación
        from utils import normalize
        self.HEADER_TYPES_NORMALIZED = [normalize(t) for t in self.HEADER_TYPES]
        # Asegurar que EMAIL_FROM tenga fallback a SMTP_USER
        # EMAIL_FROM ya viene del .env, no hay fallback SMTP
 
    def validate(self) -> list[str]:
        """Retorna lista de errores de configuración."""
        errors = []
        if not self.MS_TENANT_ID:
            errors.append("MS_TENANT_ID no configurado")
        if not self.MS_CLIENT_ID:
            errors.append("MS_CLIENT_ID no configurado")
        if not self.MS_CLIENT_SECRET:
            errors.append("MS_CLIENT_SECRET no configurado")
        if not self.EMAIL_FROM:
            errors.append("EMAIL_FROM no configurado")
        if not self.EMAIL_TO:
            errors.append("EMAIL_TO no configurado")
        return errors
 
 
config = Config()
 