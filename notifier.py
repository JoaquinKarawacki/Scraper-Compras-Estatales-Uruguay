"""
notifier.py
-----------
Envío de emails via Microsoft Graph API (OAuth2 Client Credentials).
Recomendado para Microsoft 365 empresarial con app registrada en Azure AD.
 
Requiere en .env:
    MS_TENANT_ID     = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    MS_CLIENT_ID     = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    MS_CLIENT_SECRET = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    EMAIL_FROM       = remitente@empresa.com  (debe tener buzón activo)
    EMAIL_TO         = destino@empresa.com
"""
 
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional
 
from config import config
 
logger = logging.getLogger(__name__)
 
 
# ---------------------------------------------------------------------------
# Autenticación OAuth2 — obtener access token
# ---------------------------------------------------------------------------
 
def get_access_token() -> Optional[str]:
    """
    Obtiene un access token de Microsoft Identity Platform
    usando Client Credentials Flow.
    """
    url = f"https://login.microsoftonline.com/{config.MS_TENANT_ID}/oauth2/v2.0/token"
 
    data = urllib.parse.urlencode({
        "grant_type":    "client_credentials",
        "client_id":     config.MS_CLIENT_ID,
        "client_secret": config.MS_CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
    }).encode("utf-8")
 
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
 
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            token = result.get("access_token")
            if token:
                logger.debug("Access token obtenido correctamente.")
                return token
            else:
                logger.error(f"Respuesta sin access_token: {result}")
                return None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.error(f"Error HTTP al obtener token: {e.code} — {body}")
        _explain_auth_error(e.code, body)
        return None
    except Exception as e:
        logger.error(f"Error al obtener token: {e}")
        return None
 
 
def _explain_auth_error(code: int, body: str):
    """Imprime sugerencias según el error de autenticación."""
    if "AADSTS700016" in body:
        logger.error("→ Client ID no encontrado. Verificar MS_CLIENT_ID en .env")
    elif "AADSTS7000215" in body:
        logger.error("→ Client Secret inválido. Verificar MS_CLIENT_SECRET en .env")
    elif "AADSTS700054" in body:
        logger.error("→ Tenant ID incorrecto. Verificar MS_TENANT_ID en .env")
    elif "AADSTS65001" in body:
        logger.error("→ Falta consentimiento de admin. En Azure Portal: API Permissions → Grant admin consent")
 
 
# ---------------------------------------------------------------------------
# Generación del email HTML y texto plano
# ---------------------------------------------------------------------------
 
def build_email_html(items: list[dict], run_at: datetime) -> str:
    run_str = run_at.strftime("%d/%m/%Y %H:%M:%S UTC")
    count = len(items)
 
    if count == 0:
        body_content = """
        <div class="empty">
            <p>✅ No se encontraron nuevas oportunidades en esta ejecución.</p>
        </div>"""
    else:
        cards = ""
        for item in items:
            kw_badges = ""
            for kw in item.get("matched_keywords", []):
                clean_kw = kw.replace("s?", "").replace("\\", "")
                kw_badges += f'<span class="badge">{clean_kw}</span>'
 
            url         = item.get("url", "#")
            title       = item.get("title") or "Sin título"
            organism    = item.get("organism") or "Organismo no especificado"
            description = item.get("description") or item.get("full_text", "")[:300]
            date_str    = item.get("date") or ""
            pub_id      = item.get("id", "")
 
            date_html = f'<span class="date">📅 {date_str}</span>' if date_str else ""
            id_html   = f'<span class="pub-id">ID: {pub_id}</span>' if pub_id else ""
 
            cards += f"""
            <div class="card">
                <div class="card-header">
                    <a href="{url}" class="card-title" target="_blank">{title}</a>
                    <div class="card-meta">
                        <span class="organism">🏛️ {organism}</span>
                        {date_html}
                        {id_html}
                    </div>
                </div>
                <div class="card-body">
                    <p class="description">{description[:400]}{"..." if len(description) > 400 else ""}</p>
                    <div class="keywords"><strong>Keywords:</strong> {kw_badges}</div>
                    <a href="{url}" class="btn-link" target="_blank">Ver publicación →</a>
                </div>
            </div>"""
        body_content = cards
 
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f4f6f9;margin:0;padding:20px;color:#333}}
  .container{{max-width:700px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.1)}}
  .header{{background:linear-gradient(135deg,#1a4a7a,#2166ac);color:white;padding:24px 30px}}
  .header h1{{margin:0 0 8px;font-size:20px}}.header p{{margin:0;font-size:13px;opacity:.85}}
  .summary-bar{{background:#e8f4fd;border-left:4px solid #2166ac;padding:12px 20px;font-size:14px;color:#1a4a7a}}
  .content{{padding:20px 30px 30px}}
  .card{{border:1px solid #e2e8f0;border-radius:6px;margin-bottom:18px;overflow:hidden}}
  .card-header{{background:#f8fafc;padding:14px 18px;border-bottom:1px solid #e2e8f0}}
  .card-title{{display:block;font-size:15px;font-weight:600;color:#1a4a7a;text-decoration:none;margin-bottom:6px;line-height:1.4}}
  .card-meta{{font-size:12px;color:#64748b;display:flex;flex-wrap:wrap;gap:12px}}
  .date{{color:#7c3aed}}.pub-id{{color:#94a3b8}}
  .card-body{{padding:14px 18px}}
  .description{{font-size:13px;color:#475569;line-height:1.6;margin:0 0 12px}}
  .keywords{{margin-bottom:12px;font-size:12px}}
  .badge{{display:inline-block;background:#dbeafe;color:#1e40af;border-radius:12px;padding:2px 10px;margin:2px;font-size:11px;font-weight:500}}
  .btn-link{{display:inline-block;background:#2166ac;color:white;text-decoration:none;padding:7px 16px;border-radius:4px;font-size:12px}}
  .empty{{text-align:center;padding:40px;color:#64748b;font-size:15px}}
  .footer{{background:#f8fafc;border-top:1px solid #e2e8f0;padding:14px 30px;text-align:center;font-size:11px;color:#94a3b8}}
</style></head>
<body><div class="container">
  <div class="header">
    <h1>🏗️ Oportunidades — Compras Estatales Uruguay</h1>
    <p>Ejecución automática · {run_str}</p>
  </div>
  <div class="summary-bar">
    {"🔔 <strong>" + str(count) + " nuevas oportunidades</strong> detectadas." if count > 0
     else "✅ Sin novedades en esta ejecución."}
  </div>
  <div class="content">{body_content}</div>
  <div class="footer">Monitor automático · <a href="{config.BASE_URL}" style="color:#2166ac">Ver portal</a></div>
</div></body></html>"""
 
 
def build_email_text(items: list[dict], run_at: datetime) -> str:
    run_str = run_at.strftime("%d/%m/%Y %H:%M:%S UTC")
    lines = ["="*60, "OPORTUNIDADES — COMPRAS ESTATALES URUGUAY", f"Ejecución: {run_str}", "="*60, ""]
 
    if not items:
        lines.append("No se encontraron nuevas oportunidades.")
    else:
        lines.append(f"{len(items)} nueva(s) oportunidad(es):\n")
        for i, item in enumerate(items, 1):
            kws = [k.replace("s?","").replace("\\","") for k in item.get("matched_keywords",[])]
            desc = item.get("description") or item.get("full_text","")[:200]
            lines += [
                f"[{i}] {item.get('title','Sin título')}",
                f"    Organismo : {item.get('organism','N/A')}",
                f"    Fecha     : {item.get('date','N/A')}",
                f"    Keywords  : {', '.join(kws)}",
                f"    Descripción: {desc[:200]}{'...' if len(desc)>200 else ''}",
                f"    Link      : {item.get('url','N/A')}",
                "",
            ]
    lines += ["-"*60, "Sistema de monitoreo automático", f"Portal: {config.BASE_URL}"]
    return "\n".join(lines)
 
 
# ---------------------------------------------------------------------------
# Envío via Microsoft Graph API
# ---------------------------------------------------------------------------
 
def send_email(items: list[dict], run_at: Optional[datetime] = None) -> bool:
    if run_at is None:
        run_at = datetime.now()
 
    if not items and not config.SEND_IF_EMPTY:
        logger.info("Sin novedades. Email no enviado (SEND_IF_EMPTY=False).")
        return True
 
    # Validar config
    missing = []
    for var in ["MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "EMAIL_FROM", "EMAIL_TO"]:
        if not getattr(config, var, ""):
            missing.append(var)
    if missing:
        logger.error(f"Variables faltantes en .env: {', '.join(missing)}")
        return False
 
    # Obtener token
    token = get_access_token()
    if not token:
        logger.error("No se pudo obtener access token. Email no enviado.")
        return False
 
    # Construir asunto
    count = len(items)
    suffix = f" ({count} nueva{'s' if count != 1 else ''})" if count > 0 else " (sin novedades)"
    subject = config.EMAIL_SUBJECT + suffix
 
    # Construir destinatarios
    recipients = [
        {"emailAddress": {"address": r.strip()}}
        for r in config.EMAIL_TO.split(",") if r.strip()
    ]
 
    # Construir payload Graph API
    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": build_email_html(items, run_at),
            },
            "toRecipients": recipients,
        },
        "saveToSentItems": "false",
    }
 
    payload_bytes = json.dumps(payload).encode("utf-8")
    send_url = f"https://graph.microsoft.com/v1.0/users/{config.EMAIL_FROM}/sendMail"
 
    req = urllib.request.Request(send_url, data=payload_bytes, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
 
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Graph devuelve 202 Accepted al éxito
            logger.info(f"✅ Email enviado via Graph API. Status: {resp.status} | {count} oportunidades.")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.error(f"Error HTTP al enviar email: {e.code} — {body}")
        if e.code == 403:
            logger.error("→ Permiso denegado. Verificar que la app tenga 'Mail.Send' en API Permissions y que el admin haya dado consentimiento.")
        elif e.code == 404:
            logger.error(f"→ Usuario '{config.EMAIL_FROM}' no encontrado. Verificar EMAIL_FROM en .env")
        elif e.code == 401:
            logger.error("→ Token inválido o expirado.")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al enviar email: {e}")
        return False