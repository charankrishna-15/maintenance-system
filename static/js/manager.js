"use strict";

/* ---------- tabs ---------- */
const TABS = ["overview", "requests", "staff"];
function showTab(name) {
  TABS.forEach((t) => {
    document.getElementById(`view-${t}`).classList.toggle("hidden", t !== name);
    document.getElementById(`tab-${t}`).setAttribute("aria-selected", String(t === name));
  });
  if (name === "overview") loadOverview();
  if (name === "requests") loadRequests();
  if (name === "staff") loadStaff();
}
TABS.forEach((t) => document.getElementById(`tab-${t}`).addEventListener("click", () => showTab(t)));

/* ---------- overview ---------- */
function barRows(el, data, classPrefix) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v || 0));
  el.innerHTML = entries.map(([label, value]) => {
    const cls = classPrefix ? `${classPrefix}-${label.replace(/ /g, "-")}` : "";
    const width = value ? Math.max(3, (value / max) * 100) : 0;
    return `<div class="bar-row"><span>${esc(label)}</span>
      <div class="bar-track"><div class="bar-fill ${esc(cls)}" style="width:${width}%"></div></div>
      <span class="bar-val">${esc(value)}</span></div>`;
  }).join("");
}

function resolutionRows(el, data) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v || 0));
  el.innerHTML = entries.map(([label, value]) => {
    const width = value ? Math.max(3, (value / max) * 100) : 0;
    return `<div class="bar-row"><span>${esc(label)}</span>
      <div class="bar-track"><div class="bar-fill u-${esc(label)}" style="width:${width}%"></div></div>
      <span class="bar-val" style="white-space:nowrap">${esc(value === null ? "-" : fmtHours(value))}</span></div>`;
  }).join("");
  el.querySelectorAll(".bar-row").forEach((r) => { r.style.gridTemplateColumns = "96px 1fr 64px"; });
}

function trendChart(el, days) {
  const W = 1000, H = 200, padL = 24, padB = 22, padT = 8;
  const max = Math.max(1, ...days.flatMap((d) => [d.created, d.resolved]));
  const slot = (W - padL) / days.length;
  const barW = Math.min(14, slot / 2 - 2);
  const y = (v) => padT + (H - padB - padT) * (1 - v / max);
  let svg = `<svg class="trend" viewBox="0 0 ${W} ${H}" role="img" aria-label="Requests submitted and resolved per day over the last 14 days">`;
  [0, 0.5, 1].forEach((f) => {
    const v = Math.round(max * f);
    svg += `<line x1="${padL}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#e1e5ef"/>` +
           `<text x="0" y="${y(v) + 3}">${v}</text>`;
  });
  days.forEach((d, i) => {
    const cx = padL + slot * i + slot / 2;
    const label = d.date.slice(5);
    svg += `<rect class="created" x="${cx - barW - 1}" y="${y(d.created)}" width="${barW}" height="${H - padB - y(d.created)}" rx="2"><title>${esc(d.date)}: ${d.created} submitted</title></rect>`;
    svg += `<rect class="resolved" x="${cx + 1}" y="${y(d.resolved)}" width="${barW}" height="${H - padB - y(d.resolved)}" rx="2"><title>${esc(d.date)}: ${d.resolved} resolved</title></rect>`;
    if (i % 2 === 0) svg += `<text x="${cx}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`;
  });
  el.innerHTML = svg + "</svg>";
}

async function loadOverview() {
  try {
    const a = await api.get("/api/analytics");
    const s = a.summary;
    const tiles = [
      ["Total requests", s.total, "All time", false],
      ["Waiting for assignment", s.open, "Status: Open", s.open > 0],
      ["In progress", s.in_progress, "Being worked on now", false],
      ["Overdue", s.overdue, "Past SLA target", s.overdue > 0],
      ["Critical active", s.critical_active, "Unresolved emergencies", s.critical_active > 0],
      ["Avg. resolution", fmtHours(s.avg_resolution_hours), "Submission to resolved", false],
      ["SLA compliance", fmtPct(s.sla_compliance_pct), "Resolved within target", false],
      ["Manager overrides", fmtPct(s.override_rate_pct), "Predicted urgency corrected", false],
    ];
    document.getElementById("kpis").innerHTML = tiles.map(([label, value, hint, alert]) => `
      <div class="tile ${alert ? "alert" : ""}"><div class="label">${esc(label)}</div>
      <div class="value">${esc(value)}</div><div class="hint">${esc(hint)}</div></div>`).join("");
    barRows(document.getElementById("chart-status"), a.by_status, "s");
    barRows(document.getElementById("chart-urgency"), a.by_urgency, "u");
    barRows(document.getElementById("chart-category"), a.by_category, "");
    resolutionRows(document.getElementById("chart-resolution"), a.avg_resolution_by_urgency);
    trendChart(document.getElementById("chart-trend"), a.daily);
    document.getElementById("perf-body").innerHTML = a.staff.length ? a.staff.map((m) => `
      <tr><td><div class="title">${esc(m.name)}</div>${m.active ? "" : '<div class="sub">Inactive</div>'}</td>
      <td>${esc(m.specialty)}</td><td>${esc(m.active_requests)}</td><td>${esc(m.resolved)}</td>
      <td>${esc(fmtHours(m.avg_resolution_hours))}</td><td>${esc(fmtPct(m.sla_compliance_pct))}</td>
      <td class="${m.overdue ? "overdue" : ""}">${esc(m.overdue)}</td></tr>`).join("")
      : `<tr><td colspan="7" class="empty">No technicians yet.</td></tr>`;
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- requests ---------- */
const reqBody = document.getElementById("requests-body");
let staffList = [];
let requests = [];

function currentFilters() {
  const p = new URLSearchParams();
  const map = { q: "f-q", status: "f-status", urgency: "f-urgency", category: "f-category" };
  Object.entries(map).forEach(([k, id]) => {
    const v = document.getElementById(id).value.trim();
    if (v) p.set(k, v);
  });
  p.set("sort", "priority");
  return p.toString();
}

async function loadRequests() {
  try {
    const res = await api.get(`/api/requests?${currentFilters()}`);
    requests = res.requests;
    const waiting = requests.filter((r) => r.status === "Open").length;
    document.getElementById("auto-assign-btn").textContent =
      waiting ? `Auto-assign waiting requests (${waiting})` : "Auto-assign waiting requests";
    document.getElementById("requests-count").textContent = `${res.count} request${res.count === 1 ? "" : "s"} shown. Click a row to manage it.`;
    reqBody.innerHTML = requests.length ? requests.map((r) => `
      <tr class="clickable" data-id="${esc(r.id)}">
        <td>${esc(r.id)}</td>
        <td><div class="title">${esc(r.title)}</div><div class="sub">${esc(r.category)} &middot; ${esc(r.tenant_name)}</div></td>
        <td>${esc(r.unit || "-")}</td><td>${urgencyBadge(r.urgency)}</td><td>${statusBadge(r.status)}</td>
        <td>${r.staff_name ? esc(r.staff_name) : '<span class="muted">Unassigned</span>'}</td>
        <td>${dueHtml(r)}</td></tr>`).join("")
      : `<tr><td colspan="7" class="empty">No requests match these filters.</td></tr>`;
  } catch (err) {
    reqBody.innerHTML = `<tr><td colspan="7" class="empty">${esc(err.message)}</td></tr>`;
  }
}

let filterTimer = null;
["f-status", "f-urgency", "f-category"].forEach((id) =>
  document.getElementById(id).addEventListener("change", loadRequests));
document.getElementById("f-q").addEventListener("input", () => {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(loadRequests, 300);
});

document.getElementById("auto-assign-btn").addEventListener("click", async (e) => {
  const button = e.currentTarget;
  setBusy(button, true, "Assigning...");
  try {
    const res = await api.post("/api/requests/auto-assign");
    toast(res.assigned ? `${res.assigned} request(s) assigned.` : "Nothing to assign (no waiting requests or no technicians).", res.assigned ? "success" : "info");
    await loadRequests();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setBusy(button, false);
    loadRequests();
  }
});

reqBody.addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-id]");
  if (row) manageRequest(row.dataset.id);
});

async function manageRequest(id) {
  try {
    const [detail, staffRes] = await Promise.all([
      api.get(`/api/requests/${encodeURIComponent(id)}`),
      api.get("/api/staff"),
    ]);
    const r = detail.request;
    staffList = staffRes.staff.filter((s) => s.active);
    const resolved = r.status === "Resolved";

    const staffOptions = staffList.map((s) => `
      <option value="${esc(s.id)}" ${s.id === r.assigned_to ? "selected" : ""}>
        ${esc(s.name)} - ${esc(s.specialty)} (${esc(s.active_requests)} active)</option>`).join("");
    const urgencyOptions = ["Low", "Medium", "High", "Critical"].map((u) =>
      `<option ${u === r.urgency ? "selected" : ""}>${u}</option>`).join("");

    const manage = resolved ? `
      <div class="manage">
        <p><strong>Resolution:</strong> ${esc(r.resolution_notes || "-")}</p>
        <div><button type="button" class="btn secondary" id="reopen-btn">Re-open request</button></div>
      </div>` : `
      <div class="manage">
        <form class="inline-form" id="assign-form">
          <div class="field"><label for="assign-staff">${r.assigned_to ? "Reassign to" : "Assign to"}</label>
            <select id="assign-staff">${staffOptions || "<option value=''>No technicians</option>"}</select></div>
          <button type="submit" class="btn" ${staffList.length ? "" : "disabled"}>${r.assigned_to ? "Reassign" : "Assign"}</button>
        </form>
        <form class="inline-form" id="urgency-form">
          <div class="field"><label for="urgency-select">Override urgency</label>
            <select id="urgency-select">${urgencyOptions}</select></div>
          <button type="submit" class="btn secondary">Update urgency</button>
        </form>
      </div>`;

    const modalBody = openModal(`Request #${esc(r.id)}`, requestDetailHtml(r) + manage);

    const assignForm = modalBody.querySelector("#assign-form");
    if (assignForm) assignForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const staffId = parseInt(modalBody.querySelector("#assign-staff").value, 10);
      if (!staffId) { toast("Choose a technician first.", "error"); return; }
      await act(() => api.post(`/api/requests/${encodeURIComponent(id)}/assign`, { staff_id: staffId }), "Assignment updated.");
    });
    const urgencyForm = modalBody.querySelector("#urgency-form");
    if (urgencyForm) urgencyForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await act(() => api.patch(`/api/requests/${encodeURIComponent(id)}/urgency`, {
        urgency: modalBody.querySelector("#urgency-select").value }), "Urgency updated.");
    });
    const reopen = modalBody.querySelector("#reopen-btn");
    if (reopen) reopen.addEventListener("click", () =>
      act(() => api.patch(`/api/requests/${encodeURIComponent(id)}/status`, {
        status: "In Progress", note: "Re-opened by manager" }), "Request re-opened."));
  } catch (err) {
    toast(err.message, "error");
  }
}

async function act(fn, message) {
  try {
    await fn();
    closeModal();
    toast(message, "success");
    loadRequests();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- staff ---------- */
async function loadStaff() {
  try {
    const res = await api.get("/api/staff");
    document.getElementById("staff-body").innerHTML = res.staff.length ? res.staff.map((s) => `
      <tr><td><div class="title">${esc(s.name)}</div><div class="sub">${esc(s.phone || "")}</div></td>
      <td>${esc(s.specialty)}</td><td>${esc(s.email)}</td>
      <td>${esc(s.active_requests)}</td><td>${esc(s.workload_score)}</td></tr>`).join("")
      : `<tr><td colspan="5" class="empty">No technicians yet. Add one on the left.</td></tr>`;
  } catch (err) {
    toast(err.message, "error");
  }
}

document.getElementById("staff-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("staff-error");
  const button = e.target.querySelector("button[type=submit]");
  error.textContent = "";
  setBusy(button, true, "Adding...");
  try {
    const res = await api.post("/api/staff", {
      name: document.getElementById("s-name").value,
      email: document.getElementById("s-email").value,
      specialty: document.getElementById("s-specialty").value,
      phone: document.getElementById("s-phone").value,
      password: document.getElementById("s-password").value,
    });
    toast(`Technician added.${res.auto_assigned ? " " + res.auto_assigned + " waiting request(s) assigned." : ""}`, "success");
    e.target.reset();
    loadStaff();
  } catch (err) {
    error.textContent = err.message;
  } finally {
    setBusy(button, false);
  }
});

loadOverview();
