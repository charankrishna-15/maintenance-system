/* Shared helpers for every page. No external libraries are used. */
"use strict";

const api = {
  async request(method, url, body) {
    const options = {
      method,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
    };
    if (method !== "GET") options.body = JSON.stringify(body === undefined ? {} : body);
    let res;
    try {
      res = await fetch(url, options);
    } catch (err) {
      throw new Error("Cannot reach the server. Check your connection and try again.");
    }
    let data = null;
    try { data = await res.json(); } catch (err) { /* non-JSON response */ }
    if (res.status === 401 && !url.startsWith("/api/auth/")) {
      window.location.href = "/";
      throw new Error("Session expired. Please log in again.");
    }
    if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
    return data;
  },
  get(url) { return this.request("GET", url); },
  post(url, body) { return this.request("POST", url, body); },
  patch(url, body) { return this.request("PATCH", url, body); },
};

/* ---------- formatting ---------- */
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function fmtDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return "-";
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function fmtHours(h) {
  if (h === null || h === undefined) return "-";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(1)} h`;
  return `${(h / 24).toFixed(1)} days`;
}

function fmtPct(p) { return p === null || p === undefined ? "-" : `${p}%`; }

function dueText(req) {
  if (req.status === "Resolved") {
    return req.resolved_late ? "Resolved late" : "Resolved on time";
  }
  const diffH = (new Date(req.due_at) - new Date()) / 36e5;
  if (diffH < 0) return `Overdue by ${fmtHours(-diffH)}`;
  return `Due in ${fmtHours(diffH)}`;
}

function dueHtml(req) {
  const cls = req.overdue || req.resolved_late ? "overdue" : "";
  return `<span class="${cls}">${esc(dueText(req))}</span>`;
}

function urgencyBadge(u) { return `<span class="badge u-${esc(u)}">${esc(u)}</span>`; }
function statusBadge(s) { return `<span class="badge s-${esc(s).replace(/ /g, "-")}">${esc(s)}</span>`; }

/* ---------- toasts ---------- */
function toast(message, type = "info") {
  let box = document.getElementById("toasts");
  if (!box) {
    box = document.createElement("div");
    box.id = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), type === "error" ? 6000 : 4000);
}

/* ---------- modal ---------- */
let activeModal = null;

function closeModal() {
  if (activeModal) {
    activeModal.overlay.remove();
    document.removeEventListener("keydown", activeModal.onKey);
    if (activeModal.opener && document.contains(activeModal.opener)) activeModal.opener.focus();
    activeModal = null;
  }
}

function openModal(title, bodyHtml) {
  closeModal();
  const opener = document.activeElement;
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-head">
        <h2 id="modal-title">${title}</h2>
        <button type="button" class="icon-btn" aria-label="Close" data-close>&times;</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closeModal(); });
  overlay.querySelector("[data-close]").addEventListener("click", closeModal);
  const onKey = (e) => { if (e.key === "Escape") closeModal(); };
  document.addEventListener("keydown", onKey);
  activeModal = { overlay, onKey, opener };
  const first = overlay.querySelector("textarea, select, input, .modal-body button");
  (first || overlay.querySelector("[data-close]")).focus();
  return overlay.querySelector(".modal-body");
}

/* ---------- request detail (shared by all roles) ---------- */
function requestDetailHtml(req) {
  const history = (req.history || []).map((h) => `
    <li>
      <div>${statusBadge(h.status)} <span class="muted small">${esc(fmtDate(h.created_at))}
        ${h.actor_name ? "&middot; " + esc(h.actor_name) : "&middot; System"}</span></div>
      <div class="tl-note">${esc(h.note || "")}</div>
    </li>`).join("");
  const confidence = req.confidence != null ? ` (${Math.round(req.confidence * 100)}% confidence)` : "";
  const source = req.urgency_source === "manager" ? "Set by manager"
    : req.urgency_source === "safety-rule" ? "Safety rule" : "Predicted by model";
  return `
    <div>${urgencyBadge(req.urgency)} ${statusBadge(req.status)}
      <span class="muted small">&nbsp;Request #${esc(req.id)} &middot; ${esc(req.category)}</span></div>
    <dl class="detail-grid">
      <div><dt>Tenant / Unit</dt><dd>${esc(req.tenant_name)} &middot; ${esc(req.unit || "-")}</dd></div>
      <div><dt>Assigned to</dt><dd>${req.staff_name ? esc(req.staff_name) : "Not assigned yet"}</dd></div>
      <div><dt>Submitted</dt><dd>${esc(fmtDate(req.created_at))}</dd></div>
      <div><dt>Target (SLA ${esc(req.sla_hours)}h)</dt><dd>${dueHtml(req)}</dd></div>
      <div><dt>Urgency source</dt><dd>${esc(source)}${req.urgency_source === "manager" ? "" : esc(confidence)}</dd></div>
      <div><dt>Resolution time</dt><dd>${esc(fmtHours(req.resolution_hours))}</dd></div>
    </dl>
    <h3>${esc(req.title)}</h3>
    <div class="desc-box">${esc(req.description)}</div>
    <h3 style="margin-top:1.1rem">Progress timeline</h3>
    <ul class="timeline">${history}</ul>`;
}

/* ---------- common page setup ---------- */
document.addEventListener("DOMContentLoaded", () => {
  const logout = document.getElementById("logout-btn");
  if (logout) {
    logout.addEventListener("click", async () => {
      try { await api.post("/api/auth/logout"); } finally { window.location.href = "/"; }
    });
  }
});

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) { button.dataset.label = button.textContent; button.textContent = label || "Please wait..."; }
  else if (button.dataset.label) { button.textContent = button.dataset.label; }
  button.disabled = busy;
}
