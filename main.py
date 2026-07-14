"""
main.py
-------
Punto de entrada principal del scraper.
Orquesta: scraping → filtrado → deduplicación → notificación.
 
Uso:
    python main.py                    # Ejecución normal
    python main.py --dry-run          # Solo scraping, sin enviar email ni guardar
    python main.py --force-send       # Forzar envío aunque no haya novedades
    python main.py --test-email       # Enviar email de prueba con datos ficticios
"""
 
import argparse
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
 
# Asegurar que el directorio del script esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent))
 
from config import config
from scraper import run_scraper
from storage import filter_new_publications, mark_as_notified, upsert_relevant_licitaciones
from notifier import send_email
 
 
# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------
 
def setup_logging():
    """Configura logging con rotación de archivos y salida a consola."""
    log_dir = Path(config.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
 
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
 
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
 
    # Handler: archivo con rotación
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
 
    # Handler: consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
 
 
# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------
 
def get_test_items() -> list[dict]:
    return [
        {
            "id": "TEST-001",
            "title": "Licitación Abreviada - Luminarias LED para rutas nacionales",
            "organism": "Ministerio de Transporte y Obras Públicas",
            "description": (
                "Se llama a licitación para el suministro e instalación de luminarias LED "
                "de alta eficiencia energética para iluminación de rutas. "
                "Incluye mantenimiento preventivo y correctivo por 24 meses."
            ),
            "date": "15/04/2026",
            "url": "https://www.comprasestatales.gub.uy/detalle/123456",
            "matched_keywords": ["luminarias", "eficiencia energetica", "mantenimiento"],
        },
        {
            "id": "TEST-002",
            "title": "Compra Directa - Consultoría en gestión ambiental",
            "organism": "MVOTMA",
            "description": (
                "Consultoría para elaborar plan de gestión ambiental y evaluación de impacto. "
                "Incluye diagnóstico de trafos y equipos eléctricos en instalaciones municipales."
            ),
            "date": "16/04/2026",
            "url": "https://www.comprasestatales.gub.uy/detalle/123457",
            "matched_keywords": ["consultoria", "ambiental", "trafos"],
        },
    ]
 
 
# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
 
def main():
    setup_logging()
    logger = logging.getLogger("main")
 
    parser = argparse.ArgumentParser(description="Scraper de Compras Estatales Uruguay")
    parser.add_argument("--dry-run", action="store_true",
                        help="Ejecutar sin enviar email ni guardar en base de datos")
    parser.add_argument("--force-send", action="store_true",
                        help="Forzar envío de email aunque no haya novedades")
    parser.add_argument("--test-email", action="store_true",
                        help="Enviar email de prueba con datos ficticios")
    args = parser.parse_args()
 
    run_at = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info("=" * 70)
    logger.info(f"INICIO DE EJECUCIÓN: {run_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 70)
 
    # --- Modo test ---
    if args.test_email:
        logger.info("Modo TEST: enviando email de prueba...")
        test_items = get_test_items()
        success = send_email(test_items, run_at)
        sys.exit(0 if success else 1)
 
    # --- Scraping ---
    try:
        all_relevant = run_scraper()
    except Exception as e:
        logger.error(f"Error crítico en scraping: {e}", exc_info=True)
        if not args.dry_run and config.MS_CLIENT_SECRET:
            try:
                send_email([{
                    "id": "ERROR",
                    "title": f"[ERROR] El scraper falló: {type(e).__name__}",
                    "organism": "Sistema automático",
                    "description": str(e),
                    "date": "",
                    "url": config.BASE_URL,
                    "matched_keywords": [],
                }], run_at)
                logger.info("Email de alerta de error enviado.")
            except Exception:
                pass
        sys.exit(1)
 
    # --- Deduplicación ---
    if args.dry_run:
        logger.info("[DRY RUN] Saltando deduplicación y envío.")
        logger.info(f"[DRY RUN] Se habrían notificado {len(all_relevant)} publicaciones:")
        for item in all_relevant:
            logger.info(f"  - [{item['id']}] {item.get('title', 'N/A')[:80]}")
        logger.info("FIN (dry-run)")
        sys.exit(0)

    # --- Panel web: refrescar licitaciones activas (independiente del email) ---
    try:
        upsert_relevant_licitaciones(all_relevant)
    except Exception as e:
        logger.error(f"Error actualizando panel de licitaciones: {e}", exc_info=True)

    new_items = filter_new_publications(all_relevant)
 
    # --- Notificación ---
    if not new_items and not args.force_send:
        logger.info("No hay nuevas publicaciones. Finalizando sin enviar email.")
        logger.info("=" * 70)
        logger.info(f"FIN: {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        sys.exit(0)
 
    # Forzar envío si flag activo
    original_send_if_empty = config.SEND_IF_EMPTY
    if args.force_send:
        config.SEND_IF_EMPTY = True
 
    email_sent = send_email(new_items, run_at)
 
    # Restaurar config
    config.SEND_IF_EMPTY = original_send_if_empty
 
    # --- Marcar como notificadas (solo si el email se envió) ---
    if email_sent and new_items:
        mark_as_notified(new_items)
        logger.info(f"✅ {len(new_items)} publicaciones marcadas como notificadas.")
    elif not email_sent:
        logger.error("Email no enviado. Las publicaciones NO se marcan como notificadas.")
        logger.error("Se reintentará en la próxima ejecución.")
        sys.exit(1)
 
    logger.info("=" * 70)
    logger.info(f"FIN EXITOSO: {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 70)
    sys.exit(0)
 
 
if __name__ == "__main__":
    main()