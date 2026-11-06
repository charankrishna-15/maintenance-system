"use strict";

const bodyEl = document.getElementById("queue-body");
const tilesEl = document.getElementById("tiles");
const filterEl = document.getElementById("status-filter");
let all = [];

function renderTiles() {
  const active = all.filter((r) => r.status === "Assigned" || r.status === "In Progress");
  const tiles = [
    ["To do", all.filter((r) => r.status === "Assigned").length, "Assigned, not started", false],
    ["In progress", all.filter((r) => r.status === "In Progress").length, "Currently working", false],
    ["Overdue", active.filter((r) => r.overdue).length, "Past their target time", true],
    ["Resolved", all.filter((r) => r.status === "Resolved").length, "All time", false],
  ];
  tilesEl.innerHTML = tiles.map(([label, value, hint, alert]) => `
    <div class="tile ${alert && value > 0 ? "alert" : ""}">
      <div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>
      <div class="hint">${esc(hint)}</div></div>`).join("");
}

function actionButtons(r) {
  if (r.status === "Assigned") {
    return `<button type="button" class="btn sm" data-act="start" data-id="${esc(r.id)}">Start work</button>`;
  }
  if (r.status === "In Progress") {
    return `<button type="button" class="btn sm" data-act="resolve" data-id="${esc(r.id)}">Mark resolved</button>`;
  }
  return `<span class="muted small">Done</span>`;
}

function renderTable() {
  const f = filterEl.value;
  const items = f === "Active" ? all.filter((r) => r.status === "Assigned" || r.status === "In Progress")
    : f ? all.filter((r) => r.status === f) : all;
  if (!items.length) {
    bodyEl.innerHTML = `<tr><td colspan="7" class="empty">${f === "Active"
      ? "Nothing to do right now. Great work!" : "No requests to show."}</td></tr>`;
    return;
  }
  bodyEl.innerHTML = items.map((r) => `
    <tr class="clickable" data-id="${esc(r.id)}">
      <td>${esc(r.id)}</td>
      <td><div class="title">${esc(r.title)}</div><div class="sub">${esc(r.category)} &middot; ${esc(r.tenant_name)}</div></td>
      <td>${esc(r.unit || "-")}</td>
      <td>${urgencyBadge(r.urgency)}</td>
      <td>${statusBadge(r.status)}</td>
      <td>${dueHtml(r)}</td>
      <td><div class="actions">${actionButtons(r)}</div></td>
    </tr>`).join("");
}

async function load() {
  try {
    const res = await api.get("/api/requests?sort=priority");
    all = res.requests;
    renderTiles();
    renderTable();
  } catch (err) {
    bodyEl.innerHTML = `<tr><td colspan="7" class="empty">${esc(err.message)}</td></tr>`;
  }
}

async function showDetail(id) {
  const res = await api.get(`/api/requests/${encodeURIComponent(id)}`);
  const r = res.request;
  const phone = r.tenant_phone ? `<p class="muted small">Tenant phone: ${esc(r.tenant_phone)}</p>` : "";
  openModal(`Request #${esc(r.id)}`, phone + requestDetailHtml(r));
}

function resolveDialog(id) {
  const modalBody = openModal(`Resolve request #${esc(id)}`, `
    <form id="resolve-form" novalidate>
      <div class="field"><label for="res-note">What was done?</label>
        <textarea id="res-note" maxlength="500" placeholder="e.g. Replaced the washer and tested for leaks"></textarea>
        <div class="help">This note is visible to the tenant and the manager.</div></div>
      <div class="form-error" id="res-error" role="alert"></div>
      <button class="btn" type="submit">Mark as resolved</button>
    </form>`);
  modalBody.querySelector("#resolve-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const note = modalBody.querySelector("#res-note").value.trim();
    const error = modalBody.querySelector("#res-error");
    if (note.length < 3) { error.textContent = "Please add a short note about the fix."; return; }
    const button = e.target.querySelector("button");
    setBusy(button, true, "Saving...");
    try {
      await api.patch(`/api/requests/${encodeURIComponent(id)}/status`, { status: "Resolved", note });
      closeModal();
      toast(`Request #${id} marked as resolved.`, "success");
      load();
    } catch (err) {
      error.textContent = err.message;
      setBusy(button, false);
    }
  });
}

bodyEl.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  try {
    if (btn) {
      const id = btn.dataset.id;
      if (btn.dataset.act === "start") {
        btn.disabled = true;
        await api.patch(`/api/requests/${encodeURIComponent(id)}/status`, { status: "In Progress" });
        toast(`Started work on request #${id}.`, "success");
        load();
      } else {
        resolveDialog(id);
      }
      return;
    }
    const row = e.target.closest("tr[data-id]");
    if (row) await showDetail(row.dataset.id);
  } catch (err) {
    toast(err.message, "error");
    load();
  }
});

filterEl.addEventListener("change", renderTable);
load();
setInterval(load, 30000);
