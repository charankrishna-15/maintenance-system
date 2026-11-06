"use strict";

const form = document.getElementById("request-form");
const titleEl = document.getElementById("r-title");
const categoryEl = document.getElementById("r-category");
const descEl = document.getElementById("r-description");
const predictionEl = document.getElementById("prediction");
const listEl = document.getElementById("request-list");
const filterEl = document.getElementById("status-filter");
let requestsCache = [];

/* ---------- live urgency preview ---------- */
let predictTimer = null;
let predictSeq = 0;

function schedulePrediction() {
  clearTimeout(predictTimer);
  document.getElementById("char-count").textContent = descEl.value.length;
  if (!categoryEl.value || descEl.value.trim().length < 10) {
    predictionEl.classList.add("hidden");
    return;
  }
  predictTimer = setTimeout(runPrediction, 500);
}

async function runPrediction() {
  const seq = ++predictSeq;
  try {
    const res = await api.post("/api/predict", {
      category: categoryEl.value, title: titleEl.value, description: descEl.value,
    });
    if (seq !== predictSeq) return; // a newer request is already in flight
    const pct = Math.round(res.confidence * 100);
    const note = res.source === "safety-rule"
      ? "Flagged as an emergency by our safety rules."
      : res.source === "low-confidence-default"
        ? "Not enough detail to be sure, so this defaults to Medium. Add more detail if it is worse."
        : "";
    predictionEl.innerHTML = `
      <div class="p-row"><strong>Predicted urgency</strong> ${urgencyBadge(res.label)}
        <span class="muted">Target fix within ${esc(res.sla_hours)} hours</span></div>
      <div class="meter" aria-hidden="true"><span style="width:${pct}%"></span></div>
      <div class="help">Model confidence ${pct}%. ${esc(note)}</div>`;
    predictionEl.classList.remove("hidden");
  } catch (err) {
    if (seq === predictSeq) predictionEl.classList.add("hidden");
  }
}

[titleEl, categoryEl, descEl].forEach((el) => el.addEventListener("input", schedulePrediction));
categoryEl.addEventListener("change", schedulePrediction);

/* ---------- submit ---------- */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("request-error");
  const button = document.getElementById("submit-btn");
  error.textContent = "";
  const title = titleEl.value.trim();
  const description = descEl.value.trim();
  if (title.length < 3) { error.textContent = "Please enter a short title (at least 3 characters)."; titleEl.focus(); return; }
  if (!categoryEl.value) { error.textContent = "Please choose a category."; categoryEl.focus(); return; }
  if (description.length < 10) { error.textContent = "Please describe the problem (at least 10 characters)."; descEl.focus(); return; }

  setBusy(button, true, "Submitting...");
  try {
    const res = await api.post("/api/requests", { title, category: categoryEl.value, description });
    const r = res.request;
    toast(
      `Request #${r.id} submitted. Urgency: ${r.urgency}.` +
      (r.staff_name ? ` Assigned to ${r.staff_name}.` : " Waiting for assignment."),
      "success",
    );
    form.reset();
    predictionEl.classList.add("hidden");
    document.getElementById("char-count").textContent = "0";
    await loadRequests();
  } catch (err) {
    error.textContent = err.message;
  } finally {
    setBusy(button, false);
  }
});

/* ---------- list ---------- */
function renderList() {
  const status = filterEl.value;
  const items = status ? requestsCache.filter((r) => r.status === status) : requestsCache;
  if (!items.length) {
    listEl.innerHTML = `<div class="empty">${requestsCache.length
      ? "No requests with this status." : "You have not submitted any requests yet."}</div>`;
    return;
  }
  listEl.innerHTML = items.map((r) => `
    <button type="button" class="req-card" data-id="${esc(r.id)}">
      <div class="req-top">
        <div class="req-title">#${esc(r.id)} &middot; ${esc(r.title)}</div>
        <div class="badges">${urgencyBadge(r.urgency)} ${statusBadge(r.status)}</div>
      </div>
      <div class="req-meta">
        <span>${esc(r.category)}</span>
        <span>Submitted ${esc(fmtDate(r.created_at))}</span>
        <span>${r.staff_name ? "Technician: " + esc(r.staff_name) : "Awaiting assignment"}</span>
        <span>${dueHtml(r)}</span>
      </div>
    </button>`).join("");
}

async function loadRequests() {
  try {
    const res = await api.get("/api/requests?sort=newest");
    requestsCache = res.requests;
    renderList();
  } catch (err) {
    listEl.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
  }
}

listEl.addEventListener("click", async (e) => {
  const card = e.target.closest(".req-card");
  if (!card) return;
  try {
    const res = await api.get(`/api/requests/${encodeURIComponent(card.dataset.id)}`);
    const r = res.request;
    const extra = r.status === "Resolved" && r.resolution_notes
      ? `<p><strong>Resolution:</strong> ${esc(r.resolution_notes)}</p>` : "";
    openModal(`Request #${esc(r.id)}`, extra + requestDetailHtml(r));
  } catch (err) {
    toast(err.message, "error");
  }
});

filterEl.addEventListener("change", renderList);
loadRequests();
setInterval(loadRequests, 30000); // keep statuses fresh
