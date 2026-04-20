"""
scraper.py
----------
Scraper para Compras Estatales Uruguay (comprasestatales.gub.uy).
Usa Playwright para renderizado dinámico (el contenido carga con JS).
 
Selectores confirmados por inspección del HTML real:
  - Cards:       div.item
  - Título:      .buy-object (link principal de la card)
  - Organismo:   .ue-sniped
  - Descripción: .desc-sniped
  - Fecha:       .date-list
  - Paginación:  a.next  →  href="/consultas/index/page/N"
"""
 
import re
import time
import logging
from typing import Optional
from urllib.parse import urljoin
 
from config import config
from utils import normalize
 
logger = logging.getLogger(__name__)
 
 
# ---------------------------------------------------------------------------
# Helpers de filtrado
# ---------------------------------------------------------------------------
 
def build_keyword_patterns(keywords: list[str]) -> list[re.Pattern]:
    """Compila regex para cada keyword, tolerante a tildes y plurales."""
    patterns = []
    for kw in keywords:
        norm = normalize(kw)
        escaped = re.escape(norm) + r"s?"
        patterns.append(re.compile(escaped, re.IGNORECASE))
    return patterns
 
 
def text_matches_keywords(text: str, patterns: list[re.Pattern]) -> list[str]:
    norm_text = normalize(text)
    return [p.pattern for p in patterns if p.search(norm_text)]
 
 
def text_matches_header_types(text: str) -> bool:
    norm = normalize(text)
    return any(t in norm for t in config.HEADER_TYPES_NORMALIZED)
 
 
# ---------------------------------------------------------------------------
# Parser de una página HTML → lista de dicts
# ---------------------------------------------------------------------------
 
def parse_page(html: str) -> list[dict]:
    """
    Parsea el HTML de una página de resultados.
    Cada card tiene clase 'item' y contiene:
      .buy-object  → link + título
      .ue-sniped   → organismo/unidad ejecutora
      .desc-sniped → descripción/objeto de la compra
      .date-list   → fechas
    """
    from bs4 import BeautifulSoup
    import hashlib
 
    soup = BeautifulSoup(html, "lxml")
    items = []
 
    cards = soup.select("div.item")
    logger.debug(f"  Cards encontradas en página: {len(cards)}")
 
    for card in cards:
        try:
            # --- Título y URL ---
            # El primer <a> de la card contiene el título y la URL del detalle
            # Formato: /consultas/detalle/mostrar-llamado/1/id/XXXXXX
            all_links = card.select("a[href]")
            link_tag = None
            for a in all_links:
                href_candidate = a.get("href", "")
                if "detalle" in href_candidate or "mostrar-llamado" in href_candidate:
                    link_tag = a
                    break
            # Fallback: primer link que no sea "Ofertar en línea"
            if not link_tag:
                for a in all_links:
                    if "sice" not in a.get("href", "") and "ofertar" not in a.get_text("").lower():
                        link_tag = a
                        break
 
            title = link_tag.get_text(strip=True) if link_tag else ""
            href = link_tag.get("href", "") if link_tag else ""
            full_url = urljoin(config.SITE_BASE, href) if href else ""
 
            # --- Organismo ---
            org_tag = card.select_one(".ue-sniped")
            organism = org_tag.get_text(strip=True) if org_tag else ""
 
            # --- Descripcion y fecha ---
            # .desc-sniped contiene el objeto y la fecha de recepcion
            desc_tag = card.select_one(".desc-sniped")
            desc_full = desc_tag.get_text(separator="\n", strip=True) if desc_tag else ""
 
            # Separar descripción de fecha
            date = ""
            description = desc_full
            if "Recepción de ofertas hasta:" in desc_full:
                parts = desc_full.split("Recepción de ofertas hasta:")
                description = parts[0].strip().strip('"')
                date = "Recepción hasta: " + parts[1].strip() if len(parts) > 1 else ""
            elif "hasta:" in desc_full.lower():
                lines = [l.strip() for l in desc_full.splitlines() if l.strip()]
                for i, line in enumerate(lines):
                    if "hasta:" in line.lower():
                        date = line
                        description = " ".join(lines[:i]).strip().strip('"')
                        break
 
            # --- Texto completo para búsqueda de keywords ---
            full_text = card.get_text(separator=" ", strip=True)
 
            # --- ID único: extraer de la URL ---
            pub_id = _extract_id(full_url) or hashlib.md5(full_text[:200].encode()).hexdigest()[:12]
 
            if not title:
                continue
 
            items.append({
                "id": pub_id,
                "title": title,
                "organism": organism,
                "description": description,
                "date": date,
                "url": full_url,
                "full_text": full_text,
            })
        except Exception as e:
            logger.debug(f"Error parseando card: {e}")
            continue
 
    return items
 
 
def _extract_id(url: str) -> Optional[str]:
    if not url:
        return None
    # Formato principal: /mostrar-llamado/1/id/1331088
    m = re.search(r'/id/(\d+)', url)
    if m:
        return m.group(1)
    # Fallbacks genéricos
    for pattern in [r'[?&]id=(\d+)', r'nro=(\d+)', r'/(\d{6,})(?:/|$|\?)']:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None
 
 
# ---------------------------------------------------------------------------
# Scraping con Playwright
# ---------------------------------------------------------------------------
 
def scrape_with_playwright(base_url: str) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("Playwright no instalado. Ejecutar: playwright install chromium")
        return []
 
    all_items = []
    page_num = 1
 
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-UY",
        )
        page = context.new_page()
        page.set_default_timeout(config.PAGE_TIMEOUT_MS)
 
        url = base_url
        while url and page_num <= config.MAX_PAGES:
            logger.info(f"  Cargando página {page_num}: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=config.PAGE_TIMEOUT_MS)
            except PWTimeout:
                logger.warning("  Timeout networkidle, intentando con 'load'...")
                try:
                    page.goto(url, wait_until="load", timeout=config.PAGE_TIMEOUT_MS)
                    time.sleep(3)
                except Exception as e:
                    logger.error(f"  No se pudo cargar la página: {e}")
                    break
 
            # Esperar a que aparezcan las cards
            try:
                page.wait_for_selector("div.item", timeout=15000)
            except PWTimeout:
                logger.warning("  No aparecieron cards (div.item) en esta página.")
 
            html = page.content()
            page_items = parse_page(html)
            all_items.extend(page_items)
            logger.info(f"  → {len(page_items)} publicaciones encontradas")
 
            # Buscar link de siguiente página
            next_link = page.query_selector("a.next")
            if next_link:
                next_href = next_link.get_attribute("href")
                if next_href:
                    url = urljoin(config.SITE_BASE, next_href)
                    page_num += 1
                    time.sleep(1)
                else:
                    break
            else:
                logger.info("  No hay más páginas.")
                break
 
        context.close()
        browser.close()
 
    return all_items
 
 
# ---------------------------------------------------------------------------
# Scraping con requests (fallback)
# ---------------------------------------------------------------------------
 
def scrape_with_requests(base_url: str) -> list[dict]:
    import requests
    from bs4 import BeautifulSoup
 
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-UY,es;q=0.9",
    })
 
    all_items = []
    url = base_url
    page_num = 1
 
    while url and page_num <= config.MAX_PAGES:
        logger.info(f"  Cargando página {page_num}: {url}")
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
                resp.raise_for_status()
                break
            except Exception as e:
                logger.warning(f"  Intento {attempt+1}/{config.MAX_RETRIES}: {e}")
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.RETRY_DELAY)
                else:
                    return all_items
 
        page_items = parse_page(resp.text)
        all_items.extend(page_items)
        logger.info(f"  → {len(page_items)} publicaciones encontradas")
 
        soup = BeautifulSoup(resp.text, "lxml")
        next_tag = soup.select_one("a.next")
        if next_tag and next_tag.get("href"):
            url = urljoin(config.SITE_BASE, next_tag["href"])
            page_num += 1
            time.sleep(0.8)
        else:
            break
 
    return all_items
 
 
# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
 
def run_scraper() -> list[dict]:
    """
    Ejecuta el scraper, aplica filtros y retorna publicaciones relevantes.
    """
    keyword_patterns = build_keyword_patterns(config.BODY_KEYWORDS)
 
    logger.info("=== Iniciando scraping ===")
    logger.info(f"URL: {config.BASE_URL}")
    logger.info(f"Tipos buscados: {config.HEADER_TYPES}")
    logger.info(f"Keywords: {config.BODY_KEYWORDS}")
 
    # Scraping
    if config.USE_PLAYWRIGHT:
        logger.info("Motor: Playwright (headless Chromium)")
        try:
            all_items = scrape_with_playwright(config.BASE_URL)
        except Exception as e:
            logger.error(f"Playwright falló ({e}), probando con requests...")
            all_items = scrape_with_requests(config.BASE_URL)
    else:
        logger.info("Motor: requests + BeautifulSoup")
        all_items = scrape_with_requests(config.BASE_URL)
 
    logger.info(f"Total publicaciones scraped: {len(all_items)}")
 
    # Filtrar por tipo (título) y keywords (cuerpo)
    relevant = []
    for item in all_items:
        # Filtro 1: tipo de publicación en el título
        if not text_matches_header_types(item["title"] + " " + item["full_text"]):
            continue
 
        # Filtro 2: keywords en descripción/texto completo
        matched = text_matches_keywords(
            item["description"] + " " + item["full_text"],
            keyword_patterns
        )
        if not matched:
            continue
 
        item["matched_keywords"] = matched
        relevant.append(item)
        logger.debug(f"  ✓ [{item['id']}] {item['title'][:70]} | {matched}")
 
    logger.info(f"Publicaciones relevantes tras filtros: {len(relevant)}")
    return relevant
 






