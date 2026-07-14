const ICONS = {
  clock: '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12Zm-1 2v4.41l3.3 3.3 1.4-1.42-2.7-2.7V6H9Z"/></svg>',
  check: '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M8.3 14.3 4 10l1.4-1.4 2.9 2.9L14.6 5l1.4 1.4-7.7 7.9Z"/></svg>',
  archive: '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M3 4h14v3H3V4Zm1 4h12v8H4V8Zm3 2v2h6v-2H7Z"/></svg>',
  building: '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M4 3h8v14H4V3Zm2 2v2h1V5H6Zm3 0v2h1V5H9Zm-3 4v2h1V9H6Zm3 0v2h1V9H9Zm-3 4v2h1v-2H6Zm3 0v2h1v-2H9ZM13 8h3v9h-3v-2h1v-1h-1v-2h1v-1h-1V8Z"/></svg>',
};

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function urgencia(item) {
  if (item.deadline_at === null || item.dias_restantes === null || item.dias_restantes === undefined) {
    return { clase: "neutral", label: "Sin fecha definida" };
  }
  const dias = item.dias_restantes;
  if (dias <= 3) {
    return { clase: "critical", label: dias <= 0 ? "Vence hoy" : `Vence en ${dias} día${dias === 1 ? "" : "s"}` };
  }
  if (dias <= 7) return { clase: "serious", label: `Vence en ${dias} días` };
  if (dias <= 20) return { clase: "warning", label: `Vence en ${dias} días` };
  return { clase: "good", label: `Vence en ${dias} días` };
}

function renderKeywords(keywords) {
  return (keywords || [])
    .map((k) => `<span class="badge badge-keyword">${escapeHtml(k.replace(/s\?$/, "").replace(/\\/g, ""))}</span>`)
    .join("");
}

function formatFecha(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("es-UY", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function cardHtml(item, { showActions }) {
  const u = urgencia(item);
  const desc = item.description || "";
  const descShort = desc.length > 280 ? desc.slice(0, 280) + "…" : desc;

  const estadoLabel =
    item.estado_manual === "solicitada"
      ? `Marcada como solicitada el ${formatFecha(item.estado_manual_at)}`
      : item.estado_manual === "archivada"
      ? `Archivada el ${formatFecha(item.estado_manual_at)}`
      : "";

  const actionsHtml = showActions
    ? `<div class="card-actions">
        <button class="btn btn-primary" data-action="solicitar" data-id="${escapeHtml(item.pub_id)}">
          ${ICONS.check} Ya solicité
        </button>
        <button class="btn btn-secondary" data-action="archivar" data-id="${escapeHtml(item.pub_id)}">
          ${ICONS.archive} Archivar
        </button>
      </div>`
    : estadoLabel
    ? `<div class="estado-note">${escapeHtml(estadoLabel)}</div>`
    : "";

  return `
    <div class="card" data-card-id="${escapeHtml(item.pub_id)}">
      <div class="card-header">
        <a class="card-title" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title || "Sin título")}</a>
        <div class="card-meta">
          <span class="badge badge-keyword">${ICONS.building} ${escapeHtml(item.organism || "Organismo no especificado")}</span>
          <span class="badge badge-status ${u.clase}">${ICONS.clock} ${u.label}</span>
        </div>
      </div>
      <div class="card-body">
        ${descShort ? `<p class="card-description">${escapeHtml(descShort)}</p>` : ""}
        <div class="card-keywords">${renderKeywords(item.matched_keywords)}</div>
        ${actionsHtml}
      </div>
    </div>`;
}

function renderList(containerId, items, opts) {
  const el = document.getElementById(containerId);
  if (!items.length) {
    el.innerHTML = `<div class="empty-state">No hay licitaciones en esta vista.</div>`;
    return;
  }
  el.innerHTML = items.map((it) => cardHtml(it, opts)).join("");
}

function showError(msg) {
  const banner = document.getElementById("error-banner");
  banner.textContent = msg;
  banner.style.display = "block";
}

async function fetchJson(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const err = new Error(body.detail || `Error ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

async function loadActivas() {
  try {
    const data = await fetchJson("/api/activas?limit=200");
    renderList("list-activas", data.items, { showActions: true });
  } catch (e) {
    showError("No se pudieron cargar las licitaciones activas: " + e.message);
  }
}

async function loadSolicitadas() {
  try {
    const data = await fetchJson("/api/solicitadas?limit=200");
    renderList("list-solicitadas", data.items, { showActions: false });
  } catch (e) {
    showError("No se pudieron cargar las licitaciones solicitadas: " + e.message);
  }
}

async function loadArchivadas() {
  try {
    const data = await fetchJson("/api/archivadas?limit=200");
    renderList("list-archivadas", data.items, { showActions: false });
  } catch (e) {
    showError("No se pudieron cargar las licitaciones archivadas: " + e.message);
  }
}

async function loadStats() {
  try {
    const stats = await fetchJson("/api/stats");
    document.querySelectorAll("[data-stat]").forEach((el) => {
      const key = el.getAttribute("data-stat");
      el.textContent = stats[key] ?? "—";
    });
  } catch (e) {
    // Stats no son críticas — fallar en silencio no rompe el resto del panel.
  }
}

async function handleAction(pubId, accion, cardEl) {
  const buttons = cardEl.querySelectorAll("button");
  buttons.forEach((b) => (b.disabled = true));
  try {
    await fetchJson(`/api/licitaciones/${encodeURIComponent(pubId)}/${accion}`, { method: "POST" });
    cardEl.remove();
    loadStats();
    const listActivas = document.getElementById("list-activas");
    if (!listActivas.querySelector(".card")) {
      listActivas.innerHTML = `<div class="empty-state">No hay licitaciones en esta vista.</div>`;
    }
  } catch (e) {
    buttons.forEach((b) => (b.disabled = false));
    showError(
      e.status === 409
        ? "Esa licitación ya fue marcada por otra persona/pestaña. Actualizá la página."
        : "No se pudo actualizar la licitación: " + e.message
    );
  }
}

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.querySelector(`[data-panel="${btn.dataset.tab}"]`).classList.add("active");
    });
  });
}

function setupActions() {
  document.body.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-action]");
    if (!btn) return;
    const cardEl = btn.closest(".card");
    handleAction(btn.dataset.id, btn.dataset.action, cardEl);
  });
}

setupTabs();
setupActions();
loadStats();
loadActivas();
loadSolicitadas();
loadArchivadas();
