# Scraper Compras Estatales Uruguay

Monitor automático de publicaciones en el portal de Compras Estatales ([comprasestatales.gub.uy](https://www.comprasestatales.gub.uy)) con notificación por email via Microsoft Graph API.

---

## Estructura del proyecto

```
scraper_compras/
├── main.py              ← Orquestador principal
├── scraper.py           ← Scraping con Playwright + filtrado
├── storage.py           ← Historial de publicaciones (SQLite)
├── notifier.py          ← Generación y envío de emails (Graph API)
├── config.py            ← Configuración centralizada desde .env
├── utils.py             ← Funciones utilitarias (normalize)
├── requirements.txt     ← Dependencias Python
├── .env.example         ← Plantilla de configuración
├── test_graph.py        ← Test de conexión Microsoft Graph API
├── data/                ← Base de datos SQLite (se crea automáticamente)
└── logs/                ← Archivos de log (se crean automáticamente)
```

---

## Comandos disponibles

```bash
python main.py                 # Ejecución normal
python main.py --dry-run       # Scraping sin enviar email ni guardar en DB
python main.py --force-send    # Forzar envío aunque no haya novedades
python main.py --test-email    # Email de prueba con datos ficticios
```

---

## Configuración (.env)

Copiar `.env.example` como `.env` y completar los valores:

```bash
cp .env.example .env
```

### Variables principales

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `BASE_URL` | URL del portal a monitorear | `https://www.comprasestatales.gub.uy/consultas/` |
| `HEADER_TYPES` | Tipos de publicación a filtrar | `Licitación,Compra Directa` |
| `BODY_KEYWORDS` | Palabras clave en el cuerpo | `luminarias,trafos,mantenimiento` |
| `MAX_PAGES` | Páginas máximas a recorrer | `100` |
| `SEND_IF_EMPTY` | Enviar email si no hay novedades | `false` |

### Variables de email (Microsoft Graph API)

| Variable | Descripción |
|----------|-------------|
| `MS_TENANT_ID` | ID del directorio en Azure AD |
| `MS_CLIENT_ID` | ID de la aplicación registrada |
| `MS_CLIENT_SECRET` | Secreto de cliente (valor, no ID) |
| `EMAIL_FROM` | Remitente — debe tener buzón activo en la organización |
| `EMAIL_TO` | Destinatario(s) separados por coma |

### Permisos requeridos en Azure Portal

La app registrada en Azure AD necesita:
```
Microsoft Graph → Mail.Send → Tipo: Aplicación → Consentimiento de admin concedido
```

---

## Instalación local (Windows)

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Instalar Playwright + Chromium
playwright install chromium

# 4. Configurar
copy .env.example .env
# Editar .env con los datos reales

# 5. Probar conexión de email
python test_graph.py

# 6. Probar scraping
python main.py --dry-run

# 7. Ejecución real
python main.py
```

---

## Instalación en servidor Linux

```bash
# 1. Subir el proyecto
scp -r scraper_compras/ usuario@servidor:~/

# 2. Instalar dependencias del sistema
sudo apt-get install -y python3 python3-pip python3-venv

# 3. Crear entorno virtual e instalar
cd ~/scraper_compras
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium

# 4. Configurar
cp .env.example .env
nano .env

# 5. Probar
python main.py --dry-run
python main.py --test-email
```

### Ejecución automática con cron

```bash
# Abrir el editor de cron
crontab -e

# Cada hora
0 * * * * cd /home/usuario/scraper_compras && ./venv/bin/python main.py >> ./logs/cron.log 2>&1

# Cada 2 horas
0 */2 * * * cd /home/usuario/scraper_compras && ./venv/bin/python main.py >> ./logs/cron.log 2>&1

# Días hábiles a las 8:00 y 15:00
0 8,15 * * 1-5 cd /home/usuario/scraper_compras && ./venv/bin/python main.py >> ./logs/cron.log 2>&1
```

---

## Panel web en Railway

El scraper corre hoy en Railway como un servicio con **Cron Schedule** (`python main.py`) sobre un Volume montado (persistencia del SQLite entre corridas/deploys). El panel web (`api.py`) necesita quedar **siempre encendido** — es un proceso distinto, así que va como un **segundo servicio dentro del mismo proyecto de Railway**, apuntando al mismo repo:

1. En el proyecto de Railway: **New Service → GitHub Repo** (el mismo repo, otra vez).
2. En ese nuevo servicio:
   - **Start Command**: `uvicorn api:app --host 0.0.0.0 --port $PORT` (Railway inyecta `$PORT`, no uses un puerto fijo).
   - **Cron Schedule**: dejar vacío — este servicio debe quedar siempre corriendo, no es una tarea periódica.
   - **Volumes**: montar el **mismo Volume** que usa el servicio del scraper, en el **mismo path** (ej. `/app/data`), para que ambos lean/escriban el mismo archivo SQLite.
   - **Variables**: copiar `DB_PATH` con el mismo valor que tiene el servicio del scraper (si está seteado explícitamente ahí). Si el scraper no la seteó y usa el default, no hace falta tocarla — cae en el mismo Volume igual.
3. **Settings → Networking → Generate Domain** para obtener una URL pública del panel.
4. Verificar: abrir `https://<tu-dominio-railway>.up.railway.app/` y confirmar que aparecen las licitaciones activas.

El servicio del scraper (cron) no necesita ningún cambio de configuración — sigue ejecutando `python main.py` igual que siempre; ese script ya incluye la lógica que puebla el panel en cada corrida.

---

## Logs y mantenimiento

```bash
# Ver log en tiempo real
tail -f logs/scraper.log

# Contar publicaciones guardadas en la DB
sqlite3 data/seen_publications.db "SELECT COUNT(*) FROM seen_publications;"

# Ver últimas publicaciones notificadas
sqlite3 data/seen_publications.db "SELECT title, notified_at FROM seen_publications ORDER BY notified_at DESC LIMIT 10;"

# Limpiar registros viejos (más de 6 meses)
sqlite3 data/seen_publications.db "DELETE FROM seen_publications WHERE first_seen < date('now', '-180 days');"

# Resetear historial completo (la próxima ejecución notifica todo de nuevo)
del data\seen_publications.db        # Windows
rm data/seen_publications.db         # Linux
```

---

## Si el sitio cambia su estructura HTML

El scraper usa selectores CSS para encontrar las cards. Si deja de encontrar resultados:

1. Abrir el portal en Chrome → F12 → inspeccionar una card de resultado
2. Identificar la clase CSS del contenedor (actualmente `div.item`)
3. Actualizar en `scraper.py` la función `parse_page()` con el nuevo selector
4. Verificar con `python main.py --dry-run`

---

## Notas de producción

- Playwright consume ~200-400MB RAM por ejecución — verificar disponibilidad en el servidor
- Si hay timeouts frecuentes, aumentar `PAGE_TIMEOUT_MS=60000` en el `.env`
- El `MS_CLIENT_SECRET` expira según la configuración en Azure (máximo 24 meses) — recordar renovarlo antes de que expire
- La base de datos SQLite crece con el tiempo — ejecutar la limpieza de registros viejos periódicamente