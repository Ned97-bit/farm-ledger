const state = { year: null };

const $ = (sel) => document.querySelector(sel);

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

const TYPE_ICON = { past: "📋", current: "🌾", future: "🌱" };
const YEAR_WINDOW = 5;

function clampWindowStart(start, total) {
  return Math.max(0, Math.min(start, Math.max(0, total - YEAR_WINDOW)));
}

async function loadYears() {
  const years = await fetchJSON("/api/years"); // [{year, year_type}] ascending
  state.yearInfo = Object.fromEntries(years.map(y => [y.year, y]));
  // Sort descending (most recent first) for windowing + display
  const desc = [...years].sort((a, b) => b.year - a.year);
  state.yearsDesc = desc;
  const ids = desc.map(y => y.year);

  const saved = Number(localStorage.getItem("year"));
  state.year = ids.includes(saved) ? saved : (ids[0] ?? null);

  // Restore window start from localStorage, clamped; otherwise 0
  const savedStart = Number(localStorage.getItem("yearWindowStart")) || 0;
  state.yearWindowStart = clampWindowStart(savedStart, ids.length);

  // Ensure active year falls inside the window; if not, shift to include it.
  const activeIdx = ids.indexOf(state.year);
  if (activeIdx !== -1) {
    if (activeIdx < state.yearWindowStart) state.yearWindowStart = activeIdx;
    else if (activeIdx >= state.yearWindowStart + YEAR_WINDOW) {
      state.yearWindowStart = Math.max(0, activeIdx - YEAR_WINDOW + 1);
    }
    state.yearWindowStart = clampWindowStart(state.yearWindowStart, ids.length);
    localStorage.setItem("yearWindowStart", state.yearWindowStart);
  }

  renderYearTabs();
}

function renderYearTabs() {
  const tabs = $("#year-tabs");
  tabs.innerHTML = "";
  const desc = state.yearsDesc || [];
  const start = state.yearWindowStart || 0;
  // Window contains `YEAR_WINDOW` years starting at `start` from the desc list.
  // For tabs we actually display them left-to-right ASCENDING (oldest in window on left,
  // most-recent on right) so reading order is chronological.
  const windowDesc = desc.slice(start, start + YEAR_WINDOW);
  const windowAsc = [...windowDesc].reverse();
  for (const y of windowAsc) {
    const b = document.createElement("button");
    b.textContent = y.year;
    b.title = `${y.year_type} year (right-click to delete)`;
    if (y.year === state.year) b.classList.add("active");
    b.onclick = () => activateYear(y.year);
    b.oncontextmenu = (e) => { e.preventDefault(); deleteYearPrompt(y.year); };
    tabs.appendChild(b);
  }
  renderYearDropdown();
}

function renderYearDropdown() {
  const wrap = $("#year-dropdown-wrap");
  wrap.innerHTML = "";
  const desc = state.yearsDesc || [];
  if (desc.length <= YEAR_WINDOW) return;  // nothing to overflow

  const btn = document.createElement("button");
  btn.id = "year-dropdown-btn";
  btn.className = "year-dropdown-btn";
  btn.type = "button";
  btn.textContent = "▾";
  btn.title = "All years";
  wrap.appendChild(btn);

  const menu = document.createElement("div");
  menu.id = "year-dropdown-menu";
  menu.className = "year-dropdown-menu hidden";
  wrap.appendChild(menu);

  const start = state.yearWindowStart || 0;
  const windowIds = desc.slice(start, start + YEAR_WINDOW).map(y => y.year);
  desc.forEach(y => {
    const inView = windowIds.includes(y.year);
    const row = document.createElement("button");
    row.className = "year-dropdown-row" + (inView ? " year-in-view" : "");
    row.innerHTML = `<span>${y.year}</span><span class="yr-tag">${y.year_type}${inView ? " · in view" : ""}</span>`;
    row.onclick = () => { menu.classList.add("hidden"); activateYear(y.year); };
    menu.appendChild(row);
  });

  btn.onclick = (e) => {
    e.stopPropagation();
    menu.classList.toggle("hidden");
  };
  document.addEventListener("click", (e) => {
    if (!menu.contains(e.target) && e.target !== btn) menu.classList.add("hidden");
  }, { once: true });
}

function activateYear(year) {
  state.year = year;
  localStorage.setItem("year", year);
  // Ensure it's in the visible window
  const desc = state.yearsDesc || [];
  const idx = desc.findIndex(y => y.year === year);
  if (idx !== -1) {
    if (idx < state.yearWindowStart) state.yearWindowStart = idx;
    else if (idx >= state.yearWindowStart + YEAR_WINDOW) {
      state.yearWindowStart = Math.max(0, idx - YEAR_WINDOW + 1);
    }
    state.yearWindowStart = clampWindowStart(state.yearWindowStart, desc.length);
    localStorage.setItem("yearWindowStart", state.yearWindowStart);
  }
  renderYearTabs();
  refresh();
}

function updateTaxDayCountdown() {
  const el = $("#tax-day-countdown");
  if (!el) return;

  const year = state.year;
  const info = state.yearInfo && state.yearInfo[year];
  // Show only for active CURRENT-type years
  if (!info || info.year_type !== "current") {
    el.classList.add("hidden"); return;
  }

  // Hide once file_taxes quest is complete (fed + state filed returns present)
  const items = state.checklistItems || [];
  const fileTaxes = items.find(i => i.id === "file_taxes");
  const complete = fileTaxes && Array.isArray(fileTaxes.files) && fileTaxes.files.length > 0;
  if (complete) {
    el.classList.add("hidden"); return;
  }

  // Compute days until April 15 of this filing year (local midnight)
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const taxDay = new Date(year, 3, 15);  // month 3 = April (0-indexed)
  taxDay.setHours(0, 0, 0, 0);
  const diffDays = Math.round((taxDay - today) / (1000 * 60 * 60 * 24));

  let label, cls = "";
  if (diffDays > 14) {
    label = `📅 ${diffDays} days to Tax Day`;
  } else if (diffDays > 1) {
    label = `📅 ${diffDays} days to Tax Day`;
    cls = "urgent";
  } else if (diffDays === 1) {
    label = "📅 Tax Day is tomorrow";
    cls = "urgent";
  } else if (diffDays === 0) {
    label = "📅 Tax Day is today";
    cls = "urgent";
  } else {
    label = `⚠ Overdue by ${Math.abs(diffDays)} day${Math.abs(diffDays) === 1 ? "" : "s"}`;
    cls = "overdue";
  }

  el.textContent = label;
  el.classList.remove("hidden", "urgent", "overdue");
  if (cls) el.classList.add(cls);
}

function shiftYearWindow(delta) {
  const total = (state.yearsDesc || []).length;
  state.yearWindowStart = clampWindowStart((state.yearWindowStart || 0) + delta, total);
  localStorage.setItem("yearWindowStart", state.yearWindowStart);
  renderYearTabs();
  // If an analytics modal is open, re-render it with the new window
  if (state.activeRender && !$("#modal").classList.contains("hidden") && $("#modal").classList.contains("info-mode")) {
    state.activeRender();
  }
}

async function deleteYearPrompt(year) {
  if (!confirm(`Delete year ${year}? (Only works if input/ is empty.)`)) return;
  const r = await fetch(`/api/year?y=${year}`, { method: "DELETE" });
  if (!r.ok) {
    alert(`Cannot delete: ${await r.text()}`);
    return;
  }
  if (state.year === year) localStorage.removeItem("year");
  await loadYears();
  await refresh();
}

function itemClass(it) {
  if (it.files.length) return "ok";
  return it.required ? "missing-req" : "missing-opt";
}

function renderChecklist(data) {
  const root = $("#checklist");
  root.innerHTML = "";
  const byCat = {};
  for (const it of data.items) (byCat[it.category] ||= []).push(it);
  for (const [cat, items] of Object.entries(byCat)) {
    const h = document.createElement("div");
    h.className = "category";
    h.textContent = cat;
    root.appendChild(h);
    for (const it of items) {
      const row = document.createElement("div");
      row.className = "item " + itemClass(it);
      row.innerHTML = `<span class="dot"></span><span class="label">${it.label}</span><span class="files"></span>`;
      const filesEl = row.querySelector(".files");
      for (const f of it.files) {
        const a = document.createElement("a");
        a.href = "#"; a.textContent = "▸";
        a.title = f;
        a.onclick = (e) => { e.preventDefault(); openFile(f); };
        filesEl.appendChild(a);
      }
      wireDrop(row, it.id);
      root.appendChild(row);
    }
  }

}

function wireDrop(el, slot) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drag-over"); });
  el.addEventListener("dragleave", () => el.classList.remove("drag-over"));
  el.addEventListener("drop", async (e) => {
    e.preventDefault();
    el.classList.remove("drag-over");
    for (const f of e.dataTransfer.files) await upload(f, slot);
    refresh();
  });
}

async function upload(file, slot) {
  const fd = new FormData();
  fd.append("file", file);
  const url = `/api/upload?year=${state.year}` + (slot ? `&slot=${slot}` : "");
  await fetch(url, { method: "POST", body: fd });
}

function openFile(relPath) {
  const url = `/api/file?year=${state.year}&path=${encodeURIComponent(relPath)}`;
  const ext = relPath.split(".").pop().toLowerCase();
  const v = $("#viewer");
  $("#viewer-title").textContent = "Viewer — " + relPath;
  if (ext === "pdf") v.innerHTML = `<iframe src="${url}"></iframe>`;
  else if (["png", "jpg", "jpeg", "gif", "webp", "heic"].includes(ext)) v.innerHTML = `<img src="${url}">`;
  else v.innerHTML = `<iframe src="${url}"></iframe>`;
  state.viewerRelPath = relPath;
  state.viewerYear = state.year;
  $("#viewer-actions").classList.remove("hidden");
}

function closeFile() {
  $("#viewer").innerHTML = "Click a document to read it.";
  $("#viewer-title").textContent = "Inspect";
  $("#viewer-actions").classList.add("hidden");
  state.viewerRelPath = null;
}

async function revealFile() {
  if (!state.viewerRelPath || !state.viewerYear) return;
  // Fetch the absolute repo root via a known endpoint: we know the structure —
  // file is at <TaxesRoot>/<year>/input/<relPath>. The Flask /api/reveal endpoint
  // resolves/validates the path server-side.
  const abs = await fetchJSON(`/api/abs-path?year=${state.viewerYear}&rel=${encodeURIComponent(state.viewerRelPath)}`)
    .catch(() => null);
  if (!abs || !abs.path) { alert("Could not resolve file path."); return; }
  await fetch("/api/reveal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: abs.path }),
  });
}

if ($("#viewer-close"))  $("#viewer-close").onclick = closeFile;
if ($("#viewer-reveal")) $("#viewer-reveal").onclick = revealFile;

async function renderSummary() {
  const s = await fetchJSON(`/api/summary?year=${state.year}`);
  const g = await fetchJSON(`/api/global`);
  state.summary = s;
  state.globalHtml = g.profile_html;
  $("#missing").innerHTML = s.missing_required.length
    ? "<h3>Missing required</h3><ul>" + s.missing_required.map(m => `<li><span class="badge">!</span>${m}</li>`).join("") + "</ul>"
    : "<h3>Missing required</h3><p>None 🎉</p>";
  $("#questions-count").textContent = s.open_questions.length;
  // Files count = number of `### ` headings in Files.md
  const m = (s.files_html || "").match(/<h3[^>]*>/g);
  $("#files-count").textContent = m ? m.length : 0;
}

async function refresh() {
  document.querySelectorAll("#year-tabs button").forEach(b => b.classList.toggle("active", Number(b.textContent) === state.year));
  const data = await fetchJSON(`/api/checklist?year=${state.year}`);
  state.checklistItems = data.items || [];
  renderChecklist(data);
  await renderSummary();
  refreshRecsCount();
  updateShipButtonLabel();
  updateTaxDayCountdown();
  // Re-render an open info-modal with fresh data
  if (state.activeRender && !$("#modal").classList.contains("hidden") && $("#modal").classList.contains("info-mode")) {
    try { await state.activeRender(); } catch {}
  }
}

// Shipping Bin intake: click = file picker, drop = same path. Each file -> Claude -> modal.
(function wireIntake() {
  const zone = $("#intake-zone");
  const input = $("#intake-input");
  zone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => { onIntake([...input.files]); input.value = ""; });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    onIntake([...e.dataTransfer.files]);
  });
})();

async function onIntake(files) {
  for (const f of files) {
    const li = addRecent(f.name, "pending", "analyzing…");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch(`/api/intake?year=${state.year}`, { method: "POST", body: fd });
      const data = await r.json();
      li.className = "ok";
      li.textContent = `${f.name} — ${data.analysis?.doc_type || "unclassified"}`;
      openIntakeModal(data);
    } catch (err) {
      li.className = "err";
      li.textContent = `${f.name} — error: ${err.message}`;
    }
  }
}

function addRecent(name, cls, hint) {
  const ul = $("#intake-recent");
  const li = document.createElement("li");
  li.className = cls;
  li.textContent = `${name} — ${hint}`;
  ul.prepend(li);
  return li;
}

let pendingIntake = null;

function openIntakeModal(data) {
  pendingIntake = data;
  const a = data.analysis || {};
  const slots = data.slots || [];
  const figures = a.key_figures || {};
  const bullets = (a.profile_updates || []).map(u => `- [${u.section}] ${u.bullet}`).join("\n");
  $("#modal-title").textContent = data.status === "no_claude"
    ? "Claude not available — classify manually"
    : `Claude says: ${a.doc_type || "?"} (${Math.round((a.confidence || 0) * 100)}% confidence)`;

  const slotOptions = slots.map(s =>
    `<option value="${s.id}" ${s.id === a.slot_id ? "selected" : ""}>${s.label}</option>`
  ).join("");

  const figRows = Object.entries(figures).map(
    ([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`
  ).join("") || "<div><em>none extracted</em></div>";

  $("#modal-body").innerHTML = `
    <label>Saved as</label>
    <input id="m-filename" type="text" value="${(a.proposed_filename || '').replace(/"/g,'&quot;')}" placeholder="e.g. W-2 — Acme Corp (2025).pdf">
    <label>Document type</label>
    <select id="m-slot"><option value="">— unsorted —</option>${slotOptions}</select>
    <label>Tax year</label>
    <input id="m-year" type="number" value="${a.tax_year || ''}">
    <label>Key figures</label>
    <div class="kv">${figRows}</div>
    <label>Profile updates (one per line, format: [Section] bullet text)</label>
    <textarea id="m-bullets">${bullets}</textarea>
    <label>Notes (added to Open Questions)</label>
    <textarea id="m-notes">${a.notes || ''}</textarea>
  `;
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
  $("#modal").classList.remove("info-mode");
  pendingIntake = null;
  state.activeRender = null;
}

function openInfoModal(title, html, chatTopic) {
  $("#modal-title").textContent = title;
  let body = `<div class="md-content">${html}</div>`;
  if (chatTopic) {
    body += `<button class="modal-chat-btn" data-chat-topic="${chatTopic}">Chat with the Wizard</button>`;
  }
  $("#modal-body").innerHTML = body;
  if (chatTopic) {
    $("#modal-body .modal-chat-btn").onclick = () => startWizardTab(chatTopic);
  }
  $("#modal").classList.add("info-mode");
  $("#modal").classList.remove("hidden");
}

// Dismiss wiring: X button, ESC, backdrop click
$("#modal-close").onclick = closeModal;
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

function wireClickablePane(id, onOpen) {
  const el = document.getElementById(id);
  el.addEventListener("click", onOpen);
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } });
}
async function renderGlobalModal() {
  openInfoModal("Global Tax Profile", state.globalHtml || "<em>No global profile yet.</em>");
}
wireClickablePane("global-btn-pane", () => { state.activeRender = renderGlobalModal; renderGlobalModal(); });
async function renderProfileModal() {
  const s = state.summary;
  if (!s) return;
  const body = (s.profile_html || "<em>No Profile.md yet.</em>") + `
    <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;">
      <button id="autosync-btn" class="t-button" style="padding:8px 14px;color:#fff;background:var(--sky);border:3px solid var(--wood-shadow);box-shadow:inset -2px -2px 0 #2a6b8f,2px 2px 0 var(--wood-shadow);cursor:pointer;text-shadow:1px 1px 0 #2a6b8f;">🔁 Auto-sync now</button>
    </div>
    <p class="t-body-xs" style="color:var(--wood-dark);margin-top:6px;">
      Runs a headless Claude to refresh the Summary + fill any TBDs it can confidently answer from your docs. Also fires automatically when you close a Wizard's Tower tab.
    </p>`;
  openInfoModal(`Tax Profile — ${state.year}`, body, "profile");
  $("#autosync-btn").onclick = async () => {
    $("#autosync-btn").disabled = true;
    $("#autosync-btn").textContent = "Syncing…";
    try {
      const r = await fetch(`/api/autosync?year=${state.year}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const res = await r.json();
      alert("Auto-sync complete. " + (res.summary || ""));
      closeModal();
      refresh();
    } catch (e) {
      alert("Auto-sync failed: " + e.message);
      $("#autosync-btn").disabled = false;
      $("#autosync-btn").textContent = "🔁 Auto-sync now";
    }
  };
}
wireClickablePane("profile-btn-pane", () => { state.activeRender = renderProfileModal; renderProfileModal(); });

async function renderFilesModal() {
  const data = await fetchJSON(`/api/cpa-package/candidates?year=${state.year}`);
  const rows = data.candidates.map(c => `
    <tr>
      <td class="doc-name"><code>${c.filename}</code></td>
      <td class="doc-desc">${c.description || "<em>no description</em>"}</td>
      <td class="doc-size">${(c.size_bytes / 1024).toFixed(0)} KB</td>
    </tr>`).join("");
  const body = `
    <table class="doc-table">
      <thead><tr><th>Document</th><th>Description</th><th>Size</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="3"><em>No documents yet.</em></td></tr>`}</tbody>
    </table>`;
  openInfoModal(`Documents — ${state.year}`, body);
}
wireClickablePane("files-btn-pane", () => { state.activeRender = renderFilesModal; renderFilesModal(); });

// ---- Analytics helpers ----
function fmtMoney(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  const s = Math.abs(n).toLocaleString();
  return n < 0 ? `<span class="neg">-$${s}</span>` : `$${s}`;
}
function sumVals(obj) {
  if (!obj) return null;
  const vals = Object.values(obj).filter(v => typeof v === "number");
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
}
function statusBadge(status) {
  const map = {
    filed_return: ["filed", "✓ Filed"],
    filed:        ["filed", "✓ Filed"],
    estimated:    ["estimated", "~ estimated"],
    planning:     ["planning", "… Planning"],
  };
  const [cls, txt] = map[status] || ["planning", status];
  return `<span class="yr-badge ${cls}">${txt}</span>`;
}

function fmtMoneyShort(v) {
  if (v === null || v === undefined) return "—";
  const n = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (n >= 1e6) return sign + "$" + (n/1e6).toFixed(1) + "M";
  if (n >= 1e3) return sign + "$" + Math.round(n/1e3) + "k";
  return sign + "$" + n;
}

function groupedBarChart(years, seriesA, seriesB) {
  // Combined AGI + Tax-paid chart: two bars per year side by side.
  // seriesA = AGI (green), seriesB = Tax paid (berry). Nulls render as greyed ghost slots.
  // SVG uses viewBox + preserveAspectRatio so it scales to container width.
  const n = years.length;
  if (n === 0) return "";
  const allVals = [...seriesA, ...seriesB].filter(v => typeof v === "number").map(Math.abs);
  if (allVals.length === 0) return "";
  const maxVal = Math.max(...allVals) || 1;

  const chartW = 640, chartH = 210;
  const padL = 16, padR = 16, padT = 22, padB = 52, legendH = 14;  // legend sits in padB
  const usableW = chartW - padL - padR;
  const usableH = chartH - padT - padB;
  const groupW = usableW / n;
  const gap = 6;
  const barW = Math.max(18, (groupW - gap * 3) / 2);

  const baselineY = padT + usableH;
  const mkBar = (x, val, color, stroke, label) => {
    if (typeof val !== "number") {
      return `<rect x="${x}" y="${baselineY - 6}" width="${barW}" height="6"
               fill="var(--parchment-dark)" stroke="var(--wood)" stroke-width="1" stroke-dasharray="3,2"/>
              <text x="${x + barW/2}" y="${baselineY - 10}"
                    text-anchor="middle" class="bar-val muted">—</text>`;
    }
    const hPx = Math.max(6, Math.round((Math.abs(val) / maxVal) * usableH));
    const y = baselineY - hPx;
    return `<rect x="${x}" y="${y}" width="${barW}" height="${hPx}"
             fill="${color}" stroke="${stroke}" stroke-width="2"/>
            <text x="${x + barW/2}" y="${y - 5}" text-anchor="middle" class="bar-val">${label}</text>`;
  };

  const bars = years.map((yr, i) => {
    const gx = padL + i * groupW;
    const aX = gx + gap;
    const bX = aX + barW + gap;
    const a = seriesA[i];
    const b = seriesB[i];
    return `
      ${mkBar(aX, a, "var(--grass)", "var(--grass-dark)", fmtMoneyShort(a))}
      ${mkBar(bX, b, "var(--berry)", "#8a2515", fmtMoneyShort(b))}
      <text x="${gx + groupW/2}" y="${baselineY + 16}"
            text-anchor="middle" class="bar-yr">${yr}</text>
    `;
  }).join("");

  // Legend centered below the year labels with small padding
  const legendY = chartH - 14;
  const legendCenterX = chartW / 2;
  const legend = `
    <rect x="${legendCenterX - 68}" y="${legendY - 10}" width="12" height="12" fill="var(--grass)" stroke="var(--grass-dark)" stroke-width="2"/>
    <text x="${legendCenterX - 52}" y="${legendY}" class="bar-legend">AGI</text>
    <rect x="${legendCenterX + 8}" y="${legendY - 10}" width="12" height="12" fill="var(--berry)" stroke="#8a2515" stroke-width="2"/>
    <text x="${legendCenterX + 24}" y="${legendY}" class="bar-legend">Tax paid</text>`;

  return `<svg class="barchart" viewBox="0 0 ${chartW} ${chartH}"
               preserveAspectRatio="xMidYMid meet" shape-rendering="crispEdges">
    <line x1="${padL}" y1="${baselineY}" x2="${chartW - padR}" y2="${baselineY}"
          stroke="var(--wood-shadow)" stroke-width="2"/>
    ${bars}
    ${legend}
  </svg>`;
}

function estTag(status) {
  return status === "estimated" ? ` <span class="est-tag">(Est.)</span>` : "";
}

function renderYearSummary(y) {
  const fig = y.figures;
  const agi = fig?.income?.agi;
  const taxPaid = sumVals(fig?.tax_paid);
  const rof = fig?.refund_or_owed || {};
  const chips = [];
  const est = estTag(y.status);
  if (agi != null)      chips.push(`<span>AGI <b>${fmtMoney(agi)}</b>${est}</span>`);
  if (taxPaid != null)  chips.push(`<span>Paid <b>${fmtMoney(taxPaid)}</b>${est}</span>`);
  if (rof.federal != null || rof.state != null) {
    const fed = rof.federal != null ? fmtMoney(rof.federal) : "—";
    const st  = rof.state   != null ? fmtMoney(rof.state)   : "—";
    chips.push(`<span>Refund <b>${fed}</b> / <b>${st}</b>${est}</span>`);
  }
  const status = statusBadge(y.status);
  return `
    <summary class="ay-summary">
      <span class="ay-sum-year">${y.year}</span>
      <span class="ay-sum-type">· ${y.year_type}</span>
      ${status}
      <span class="ay-sum-metrics">${chips.join("")}</span>
      <span class="ay-sum-caret">▾</span>
    </summary>`;
}

// Single-series bar chart (e.g. refund by year). Positive → green, negative → berry.
function refundBarChart(years, values) {
  const n = years.length;
  if (n === 0) return "";
  const allVals = values.filter(v => typeof v === "number").map(Math.abs);
  if (allVals.length === 0) return "";
  const maxVal = Math.max(...allVals) || 1;

  const chartW = 640, chartH = 160;
  const padL = 16, padR = 16, padT = 18, padB = 34;  // padB holds the year-label row
  const usableW = chartW - padL - padR;
  const usableH = chartH - padT - padB;
  const barW = Math.max(28, Math.min(60, (usableW - (n - 1) * 14) / n));
  // If every value is non-negative, drop the zero-line to the bottom so positive bars can grow tall.
  // Only center the baseline when a negative (owed) value exists.
  const hasNegative = values.some(v => typeof v === "number" && v < 0);
  const midY = hasNegative ? (padT + usableH / 2) : (padT + usableH);
  const posBudget = hasNegative ? usableH / 2 : usableH;  // vertical pixels available above zero

  const bars = years.map((yr, i) => {
    const x = padL + i * (usableW / n) + (usableW / n - barW) / 2;
    const v = values[i];
    // Year label below the baseline — baseline may be mid or bottom depending on hasNegative.
    const yearLabelY = midY + 16;
    if (typeof v !== "number") {
      return `<rect x="${x}" y="${midY - 3}" width="${barW}" height="6"
               fill="var(--parchment-dark)" stroke="var(--wood)" stroke-width="1" stroke-dasharray="3,2"/>
              <text x="${x + barW/2}" y="${yearLabelY}" text-anchor="middle" class="bar-yr">${yr}</text>`;
    }
    const hPx = Math.max(6, Math.round((Math.abs(v) / maxVal) * posBudget));
    const positive = v >= 0;
    const y = positive ? midY - hPx : midY;
    const color = positive ? "var(--grass)" : "var(--berry)";
    const stroke = positive ? "var(--grass-dark)" : "#8a2515";
    const labelY = positive ? (y - 5) : (y + hPx + 12);
    return `<rect x="${x}" y="${y}" width="${barW}" height="${hPx}"
             fill="${color}" stroke="${stroke}" stroke-width="2"/>
            <text x="${x + barW/2}" y="${labelY}" text-anchor="middle" class="bar-val">${fmtMoneyShort(v)}</text>
            <text x="${x + barW/2}" y="${yearLabelY}" text-anchor="middle" class="bar-yr">${yr}</text>`;
  }).join("");

  return `<svg class="barchart" viewBox="0 0 ${chartW} ${chartH}"
               preserveAspectRatio="xMidYMid meet" shape-rendering="crispEdges">
    <line x1="${padL}" y1="${midY}" x2="${chartW - padR}" y2="${midY}"
          stroke="var(--wood-shadow)" stroke-width="2"/>
    ${bars}
  </svg>`;
}

function renderYearCard(y) {
  const fig = y.figures;
  const hasFig = !!fig;
  const agi = fig?.income?.agi;
  const split = fig?.income?.split || {};
  const taxLiab = fig?.tax_liability || {};
  const taxPaid = fig?.tax_paid || {};
  const refundOwed = fig?.refund_or_owed || {};
  const invest = fig?.investments || {};
  const retire = fig?.retirement_contributions || {};
  const liab = fig?.liabilities || {};
  const ded = fig?.deductions || {};

  const row = (label, value, nested = "") =>
    `<div class="ay-row"><span class="ay-l">${label}</span><span class="ay-v">${value}</span></div>${nested}`;
  const sub = (label, value) =>
    `<div class="ay-row ay-sub"><span class="ay-l">└ ${label}</span><span class="ay-v">${value}</span></div>`;

  const agiSplitRows = hasFig ? [
    ["Wages (W-2)",           split.wages_w2],
    ["Self-employment",       split.self_employment],
    ["Interest",              split.interest],
    ["Dividends",             split.dividends],
    ["Capital gains / losses",split.capital_gains],
    ["Retirement distrib.",   split.retirement_distrib],
    ["Other",                 split.other],
  ].filter(([, v]) => v !== null && v !== undefined)
   .map(([k, v]) => sub(k, fmtMoney(v))).join("") : "";

  const retireLine = hasFig && (retire["401k"] || retire.ira || retire.hsa || retire.rollovers)
    ? `401k ${fmtMoney(retire["401k"])} · IRA ${fmtMoney(retire.ira)} · HSA ${fmtMoney(retire.hsa)}${retire.rollovers ? " · Rollovers " + fmtMoney(retire.rollovers) : ""}`
    : "—";

  const refundLine = hasFig && (refundOwed.federal !== null || refundOwed.state !== null)
    ? `Fed ${fmtMoney(refundOwed.federal)} · State ${fmtMoney(refundOwed.state)}`
    : "—";

  const liabLine = hasFig
    ? [
        liab.underpayment_penalty_est ? `Underpayment penalty ${fmtMoney(liab.underpayment_penalty_est)}` : "",
        liab.owed_federal ? `Owed federal ${fmtMoney(liab.owed_federal)}` : "",
        liab.owed_state ? `Owed state ${fmtMoney(liab.owed_state)}` : "",
      ].filter(Boolean).join(" · ") || "—"
    : "—";

  const pct = y.required_total ? Math.round(100 * y.required_filled / y.required_total) : 0;

  const isOpen = state.openYearCards && state.openYearCards.has(y.year);
  return `
    <details class="ay-card" ${isOpen ? "open" : ""} data-year="${y.year}">
      ${renderYearSummary(y)}
      <div class="ay-docs-line">${y.docs_total} docs · ${y.required_filled}/${y.required_total} required</div>
      <div class="ay-progress"><div class="fill" style="width:${pct}%"></div></div>
      <div class="ay-body">
        ${row("AGI", fmtMoney(agi), agiSplitRows)}
        ${row("Deductions" + (ded.method ? ` (${ded.method})` : ""), fmtMoney(ded.amount))}
        ${row("Taxable income", fmtMoney(fig?.taxable_income))}
        ${row("Tax liability (total)", fmtMoney(sumVals(taxLiab)))}
        ${sub("Federal", fmtMoney(taxLiab.federal))}
        ${sub("NY State", fmtMoney(taxLiab.ny_state))}
        ${sub("NYC", fmtMoney(taxLiab.nyc))}
        ${row("Tax paid (total)", fmtMoney(sumVals(taxPaid)))}
        ${row("Refund / owed", refundLine)}
        ${row("Investments (net)", fmtMoney(invest.net_gain_loss))}
        ${invest.carryforward_out ? sub("Carryforward out", fmtMoney(invest.carryforward_out)) : ""}
        ${row("Retirement contrib.", retireLine)}
        ${row("Liabilities", liabLine)}
        ${!hasFig ? `<p class="ay-missing">No figures captured yet for this year. Run Auto-sync or open Gandalf to populate.</p>` : ""}
      </div>
    </details>`;
}

async function renderAnalyticsModal() {
  const a = await fetchJSON("/api/analytics");
  const k = a.kpis;
  const kpis = `
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-label">Years tracked</div><div class="kpi-value">${k.total_years}</div></div>
      <div class="kpi-card"><div class="kpi-label">Lifetime AGI</div><div class="kpi-value">${fmtMoney(k.lifetime_agi)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Lifetime tax paid</div><div class="kpi-value">${fmtMoney(k.lifetime_tax_paid)}</div></div>
    </div>`;

  // Years ascending for charts (chronological), descending for cards (most recent first)
  const yearsAscAll = [...a.years].sort((x, y) => x.year - y.year);
  const yearsDesc = [...a.years].sort((x, y) => y.year - x.year);

  // Apply the 5-year window to charts (in sync with header tabs)
  const total = yearsDesc.length;
  const start = state.yearWindowStart || 0;
  const windowDescYears = yearsDesc.slice(start, start + YEAR_WINDOW).map(y => y.year);
  const yearsAsc = yearsAscAll.filter(y => windowDescYears.includes(y.year));

  const yearLabels = yearsAsc.map(y => y.year);
  const agiSeries = yearsAsc.map(y => y.figures?.income?.agi ?? null);
  const taxSeries = yearsAsc.map(y => sumVals(y.figures?.tax_paid) ?? null);
  const hasAny = agiSeries.some(v => typeof v === "number") || taxSeries.some(v => typeof v === "number");
  const windowControls = total > YEAR_WINDOW
    ? `<div class="chart-window-controls">
         <button class="cw-arrow" data-delta="1" title="Older" ${start + YEAR_WINDOW >= total ? "disabled" : ""}>◂</button>
         <span class="cw-range">${yearLabels[0] || ""}–${yearLabels[yearLabels.length - 1] || ""}</span>
         <button class="cw-arrow" data-delta="-1" title="Newer" ${start <= 0 ? "disabled" : ""}>▸</button>
       </div>`
    : "";
  const chart = hasAny
    ? `<div class="spark-block">
         <div class="spark-header"><div class="spark-label">AGI &amp; Tax paid by year</div>${windowControls}</div>
         ${groupedBarChart(yearLabels, agiSeries, taxSeries)}
       </div>` : "";

  // Refund-by-year = federal + state summed per year (null if both missing)
  const refundSeries = yearsAsc.map(y => {
    const rof = y.figures?.refund_or_owed;
    if (!rof) return null;
    const fed = rof.federal, st = rof.state;
    if (typeof fed !== "number" && typeof st !== "number") return null;
    return (fed || 0) + (st || 0);
  });
  const hasRefund = refundSeries.some(v => typeof v === "number");
  const refundChart = hasRefund
    ? `<div class="spark-block">
         <div class="spark-label">Refund (Fed + State) by year</div>
         ${refundBarChart(yearLabels, refundSeries)}
       </div>` : "";

  // Initialize open-state: most recent year open by default on first render
  if (!state.openYearCards) {
    state.openYearCards = new Set();
    if (yearsDesc.length > 0) state.openYearCards.add(yearsDesc[0].year);
  }

  const cards = yearsDesc.map(renderYearCard).join("");
  const note = `<p class="ay-note">${a.note}</p>`;
  openInfoModal("Analytics", kpis + chart + refundChart + `<div class="ay-grid">${cards}</div>` + note);

  // Persist open/collapsed state across SSE-driven re-renders
  document.querySelectorAll(".ay-card[data-year]").forEach(el => {
    el.addEventListener("toggle", () => {
      const yr = Number(el.dataset.year);
      if (el.open) state.openYearCards.add(yr);
      else state.openYearCards.delete(yr);
    });
  });
  // Chart-window arrow controls: delta +1 moves window back (older), -1 moves forward
  document.querySelectorAll(".cw-arrow").forEach(btn => {
    btn.onclick = () => shiftYearWindow(Number(btn.dataset.delta));
  });
}
wireClickablePane("analytics-btn-pane", () => { state.activeRender = renderAnalyticsModal; renderAnalyticsModal(); });

async function renderQuestionsModal() {
  const s = state.summary;
  if (!s) return;
  const hasQuestions = s.open_questions.length > 0;
  const body = hasQuestions
    ? `<ul class="questions-list">${s.open_questions.map(q => `<li>${q}</li>`).join("")}</ul>`
    : "<em>No open questions.</em>";
  openInfoModal(`Open Questions — ${state.year}`, body, hasQuestions ? "questions" : null);
}
wireClickablePane("questions-btn-pane", () => { state.activeRender = renderQuestionsModal; renderQuestionsModal(); });

async function renderRecsModal() {
  const r = await fetchJSON("/api/recommendations");
  openInfoModal("Recommendations", r.html || "<em>No recommendations yet — consult the Ancient One.</em>");
}
wireClickablePane("recs-btn-pane", () => { state.activeRender = renderRecsModal; renderRecsModal(); });

async function refreshRecsCount() {
  try {
    const r = await fetchJSON("/api/recommendations");
    const html = r.html || "";
    // Count <li> under each section by walking sections in the rendered HTML
    const parser = new DOMParser();
    const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
    const headings = [...doc.querySelectorAll("h2")];
    const countAfter = (label) => {
      const h = headings.find(h => h.textContent.trim().toLowerCase().startsWith(label));
      if (!h) return 0;
      // Walk siblings until next h2
      let el = h.nextElementSibling;
      let lis = 0;
      while (el && el.tagName !== "H2") {
        if (el.tagName === "UL") {
          lis += [...el.querySelectorAll("li")]
            .filter(li => !/^\s*none yet/i.test(li.textContent.trim())).length;
        }
        el = el.nextElementSibling;
      }
      return lis;
    };
    const active = countAfter("active strategies");
    const focus  = countAfter("current focus");
    $("#recs-count").textContent = `${active} active · ${focus} to review`;
  } catch {}
}

$("#modal-cancel").onclick = async () => {
  if (pendingIntake?.saved_path) {
    await fetch(`/api/discard-intake?year=${state.year}&path=${encodeURIComponent(pendingIntake.saved_path)}`, { method: "POST" });
  }
  closeModal();
  refresh();
};

$("#modal-confirm").onclick = async () => {
  if (!pendingIntake) return;
  const payload = {
    saved_path: pendingIntake.saved_path,
    slot_id: $("#m-slot").value,
    filename: ($("#m-filename")?.value || "").trim(),
    bullets: $("#m-bullets").value,
    notes: $("#m-notes").value,
    quest_updates: pendingIntake.analysis?.quest_updates || {},
    files_md_entry: pendingIntake.analysis?.files_md_entry || "",
    new_open_questions: pendingIntake.analysis?.new_open_questions || [],
    resolved_questions: pendingIntake.analysis?.resolved_questions || [],
  };
  await fetch(`/api/commit-intake?year=${state.year}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  closeModal();
  refresh();
};

async function updateShipButtonLabel() {
  try {
    const s = await fetchJSON(`/api/cpa-package/status?year=${state.year}`);
    $("#export-btn").textContent = s.exists ? "Reship to CPA" : "Ship to CPA";
  } catch {}
}

async function openCpaPackageModal() {
  const data = await fetchJSON(`/api/cpa-package/candidates?year=${state.year}`);
  const truncate = (s, n) => {
    const plain = String(s || "").replace(/\*\*/g, "").replace(/[`*_]/g, "").trim();
    return plain.length > n ? plain.slice(0, n - 1) + "…" : plain;
  };
  const rows = data.candidates.map(c => `
    <tr>
      <td class="cpa-check"><input type="checkbox" checked data-rel="${c.rel_path}"></td>
      <td class="cpa-name"><span class="cpa-name-text">${c.filename}</span></td>
      <td class="cpa-desc">${c.description ? truncate(c.description, 140) : "<em>no description</em>"}</td>
      <td class="cpa-size">${(c.size_bytes / 1024).toFixed(0)} KB</td>
    </tr>`).join("");
  const totalCount = data.candidates.length;
  const heading = data.existing_package
    ? `<p style="font-size:var(--fs-body-sm);margin:0 0 10px;"><em>Existing package:</em> <code>${data.existing_package}</code> — regenerating will overwrite.</p>`
    : "";
  const unsortedNote = (data.unsorted_count || 0) > 0
    ? `<p style="font-size:var(--fs-body-sm);margin:0 0 10px;color:var(--berry);">⚠ ${data.unsorted_count} file(s) sitting in <code>input/unsorted/</code> — not included. Re-drop them via Shipping Bin to classify, or delete if stray.</p>`
    : "";
  const body = `
    ${heading}
    ${unsortedNote}
    <p style="font-size:var(--fs-body-sm);margin:0 0 10px;">
      <b>Author:</b> ${data.author}<br>
      <b>Output:</b> <code>${state.year}FYDocumentsPrepared_${data.author.replace(/[^A-Za-z0-9]/g,"")}.pdf</code>
    </p>
    <div class="cpa-toolbar">
      <button id="cpa-all">Select all</button>
      <button id="cpa-none">Select none</button>
      <span id="cpa-selected-count" class="cpa-count">${totalCount} of ${totalCount} selected</span>
    </div>
    <div class="cpa-table-wrap">
      <table class="cpa-table">
        <thead><tr><th></th><th>Document</th><th>Description</th><th>Size</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="4"><em>No documents in input/.</em></td></tr>`}</tbody>
      </table>
    </div>
    <button id="cpa-create" class="modal-chat-btn" style="margin-top:14px;background:var(--grass);">Create Package for CPA</button>
    <div id="cpa-result" style="margin-top:12px;"></div>`;
  openInfoModal(`Package for CPA — ${state.year}`, body);
  const updateCpaCount = () => {
    const total = document.querySelectorAll(".cpa-table input").length;
    const picked = document.querySelectorAll(".cpa-table input:checked").length;
    const el = $("#cpa-selected-count");
    if (el) el.textContent = `${picked} of ${total} selected`;
    const btn = $("#cpa-create");
    if (btn && !btn.disabled) btn.textContent = `Create Package for CPA (${picked})`;
  };
  document.querySelectorAll(".cpa-table input").forEach(cb => cb.addEventListener("change", updateCpaCount));
  $("#cpa-all").onclick  = () => { document.querySelectorAll(".cpa-table input").forEach(cb => cb.checked = true);  updateCpaCount(); };
  $("#cpa-none").onclick = () => { document.querySelectorAll(".cpa-table input").forEach(cb => cb.checked = false); updateCpaCount(); };
  updateCpaCount();
  $("#cpa-create").onclick = async () => {
    const selected = [...document.querySelectorAll(".cpa-table input:checked")].map(cb => cb.dataset.rel);
    if (!selected.length) { alert("Select at least one document."); return; }
    $("#cpa-create").disabled = true;
    $("#cpa-create").textContent = "Building PDF…";
    try {
      const r = await fetch(`/api/cpa-package?year=${state.year}`, {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ selected }),
      });
      if (!r.ok) throw new Error(await r.text());
      const result = await r.json();
      $("#cpa-result").innerHTML = `
        <div class="cpa-success">
          <b>✓ Package ready</b><br>
          <code>${result.filename}</code> · ${result.pages} pages · ${result.included.length} documents
          ${result.skipped.length ? `<br><em>Skipped: ${result.skipped.join(", ")}</em>` : ""}
          <div style="margin-top:8px;">
            <button id="cpa-reveal">Reveal in Finder</button>
          </div>
        </div>`;
      $("#cpa-reveal").onclick = () => fetch("/api/reveal", {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ path: result.path }),
      });
      updateShipButtonLabel();
      refresh();
    } catch (e) {
      $("#cpa-result").innerHTML = `<div class="cpa-error">Failed: ${e.message}</div>`;
    } finally {
      $("#cpa-create").disabled = false;
      const picked = document.querySelectorAll(".cpa-table input:checked").length;
      $("#cpa-create").textContent = `Create Package for CPA (${picked})`;
    }
  };
}

// Quests that aren't prerequisites for shipping to CPA — they're outcomes of the workflow.
// `file_taxes` is completed AFTER the CPA files the return; `cpa_package` is produced BY this very action.
const SHIP_READY_EXCLUDE = new Set(["file_taxes", "cpa_package"]);

async function startShipToCpa() {
  const [cl, sm] = await Promise.all([
    fetchJSON(`/api/checklist?year=${state.year}`),
    fetchJSON(`/api/summary?year=${state.year}`),
  ]);
  const gateItems = cl.items.filter(i => !SHIP_READY_EXCLUDE.has(i.id));
  const requiredMissing = gateItems.filter(i => i.required && i.files.length === 0);
  const optionalEmpty   = gateItems.filter(i => !i.required && i.files.length === 0);
  const requiredTotal   = gateItems.filter(i => i.required).length;
  const optionalTotal   = gateItems.filter(i => !i.required).length;
  const openQs = sm.open_questions || [];
  const ready = requiredMissing.length === 0 && openQs.length === 0;

  if (ready) {
    openCpaPackageModal();
    return;
  }
  openPreflightModal({ requiredMissing, requiredTotal, optionalEmpty, optionalTotal, openQs });
}

function openPreflightModal({ requiredMissing, requiredTotal, optionalEmpty, optionalTotal, openQs }) {
  const kpis = `
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-label">Required</div><div class="kpi-value">${requiredTotal - requiredMissing.length}/${requiredTotal}</div></div>
      <div class="kpi-card"><div class="kpi-label">Optional</div><div class="kpi-value">${optionalTotal - optionalEmpty.length}/${optionalTotal}</div></div>
      <div class="kpi-card"><div class="kpi-label">Open Qs</div><div class="kpi-value">${openQs.length}</div></div>
    </div>`;
  // Sections only render when they have rows; empty sections are hidden entirely.
  const section = (title, rows, cls) => rows.length === 0 ? "" : `
    <section class="preflight-section">
      <h3 class="${cls}">${title} (${rows.length})</h3>
      <ul class="preflight-list">${rows.map(r => `<li>${r}</li>`).join("")}</ul>
    </section>`;
  const body = `
    ${kpis}
    ${section("❗ Required missing",
              requiredMissing.map(i => `<span class="dot-red"></span> ${i.label}`), "preflight-req")}
    ${section("❓ Open questions",
              openQs.map(q => q), "preflight-qs")}
    ${section("⚠ Optional empty (FYI)",
              optionalEmpty.map(i => `<span class="dot-grey"></span> ${i.label}`), "preflight-opt")}
    <div class="preflight-actions">
      <button id="pf-wizard"  class="t-button preflight-btn preflight-btn-primary">🧙 Chat with Wizard to resolve</button>
      <button id="pf-proceed" class="t-button preflight-btn preflight-btn-ghost">📦 Proceed anyway</button>
      <button id="pf-cancel"  class="t-button preflight-btn preflight-btn-ghost">Cancel</button>
    </div>`;
  openInfoModal(`Ship to CPA — readiness check`, body);
  $("#pf-wizard").onclick = () => { closeModal(); startWizardTab("ship-readiness"); };
  $("#pf-proceed").onclick = () => { closeModal(); openCpaPackageModal(); };
  $("#pf-cancel").onclick = closeModal;
}

$("#export-btn").onclick = startShipToCpa;

// ---- New Year wizard ----
const TYPE_DESC = {
  past:    { icon: "📋", name: "Past",    desc: "Already filed. For reference, carryforwards, and Q&A." },
  current: { icon: "🌾", name: "Current", desc: "Being prepared now for CPA handoff." },
  future:  { icon: "🌱", name: "Future",  desc: "Planning. Estimated payments, projections, life events." },
};

let wiz = null;

function renderWizStep() {
  if (!wiz) return;
  const totalSteps = wiz.type === "past" ? 6 : 3;
  $("#modal-title").textContent = `New Year — Step ${wiz.step} of ${totalSteps}`;
  $("#modal").classList.remove("info-mode");
  // Button labels per step
  const confirmLabel = {
    1: "Next ›", 2: "Next ›", 3: wiz.type === "past" ? "Create & continue ›" : "Create year",
    4: "Next ›", 5: "Process ›", 6: "Processing…",
  }[wiz.step] || "Next ›";
  $("#modal-confirm").textContent = confirmLabel;
  $("#modal-confirm").disabled = wiz.step === 6;
  $("#modal-cancel").textContent  = wiz.step === 1 ? "Cancel" : "‹ Back";
  $("#modal-cancel").disabled = wiz.step === 6;

  const body = $("#modal-body");
  if (wiz.step === 1) {
    body.innerHTML = `
      <div class="wiz-step">
        <label>Filing year</label>
        <input id="wiz-year" type="number" min="2000" max="2099" value="${wiz.year}">
        <p style="margin-top:8px;font-size:var(--fs-body-xs);color:var(--wood-dark);">Folder name = the calendar year the return is filed (covers the prior year's income). Current default year: <strong>${wiz.currentFiling}</strong>.</p>
      </div>`;
  } else if (wiz.step === 2) {
    const cards = Object.entries(TYPE_DESC).map(([key, t]) => `
      <div class="wiz-type ${wiz.type === key ? 'selected' : ''}" data-type="${key}">
        <span class="wiz-icon">${t.icon}</span>
        <div class="wiz-name">${t.name}</div>
        <div class="wiz-desc">${t.desc}</div>
      </div>`).join("");
    body.innerHTML = `
      <div class="wiz-step">
        <label>What kind of year is ${wiz.year}?</label>
        <div class="wiz-types">${cards}</div>
        <p style="margin-top:8px;font-size:var(--fs-body-xs);color:var(--wood-dark);">Auto-picked as <strong>${wiz.autoType}</strong> based on the current filing year (${wiz.currentFiling}). Override if your situation differs.</p>
      </div>`;
    body.querySelectorAll(".wiz-type").forEach(el => {
      el.onclick = () => { wiz.type = el.dataset.type; renderWizStep(); };
    });
  } else if (wiz.step === 3) {
    const t = TYPE_DESC[wiz.type];
    body.innerHTML = `
      <div class="wiz-step">
        <label>Confirm</label>
        <div class="wiz-confirm-summary">
          Creating <strong>${wiz.year}</strong> as a <strong>${t.name.toLowerCase()}</strong> year ${t.icon}.<br><br>
          ${wiz.type === 'past'    ? "We'll scaffold the year, then ask for your federal and state filed returns so Claude can populate everything." : ""}
          ${wiz.type === 'current' ? "We'll scaffold the full intake checklist (W-2s, 1099s, HSA, etc.) and standard Profile sections." : ""}
          ${wiz.type === 'future'  ? "We'll scaffold Profile.md with <em>Projected Income</em>, <em>Estimated Payments</em>, and <em>Life Events</em>, and a checklist focused on quarterly estimates." : ""}
        </div>
      </div>`;
  } else if (wiz.step === 4) {
    body.innerHTML = `
      <div class="wiz-step">
        <label>Federal return — ${wiz.year}</label>
        <p style="font-size:var(--fs-body-sm);color:var(--wood-dark);margin:0 0 10px;">Drop your filed federal 1040 PDF (including schedules if separate). Required.</p>
        <div id="wiz-fed-zone" class="dropzone" style="cursor:pointer;">Drop 1040 PDF here — or click to browse</div>
        <input type="file" id="wiz-fed-input" accept="application/pdf,image/*" style="display:none">
        <div id="wiz-fed-status" class="wiz-upload-status"></div>
      </div>`;
    const zone = $("#wiz-fed-zone"), input = $("#wiz-fed-input"), statusEl = $("#wiz-fed-status");
    zone.onclick = () => input.click();
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", async (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      const f = e.dataTransfer.files[0];
      if (f) { wiz.fedUploaded = await wizHandleUpload(f, "filed_return", statusEl); }
    });
    input.onchange = async () => {
      const f = input.files[0];
      if (f) { wiz.fedUploaded = await wizHandleUpload(f, "filed_return", statusEl); }
    };
  } else if (wiz.step === 5) {
    body.innerHTML = `
      <div class="wiz-step">
        <label>State return — ${wiz.year}</label>
        <p style="font-size:var(--fs-body-sm);color:var(--wood-dark);margin:0 0 10px;">Drop your state return PDF (IT-201 for NY, or your state's equivalent). Skip if your state has no income tax.</p>
        <div id="wiz-state-zone" class="dropzone" style="cursor:pointer;">Drop state return PDF here — or click to browse</div>
        <input type="file" id="wiz-state-input" accept="application/pdf,image/*" style="display:none">
        <div id="wiz-state-status" class="wiz-upload-status"></div>
        <p style="font-size:var(--fs-body-xs);color:var(--wood-dark);margin-top:10px;">
          No state income tax? Click <strong>Process ›</strong> to continue without a state return.
        </p>
      </div>`;
    const zone = $("#wiz-state-zone"), input = $("#wiz-state-input"), statusEl = $("#wiz-state-status");
    zone.onclick = () => input.click();
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", async (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      const f = e.dataTransfer.files[0];
      if (f) { await wizHandleUpload(f, "state_return", statusEl); }
    });
    input.onchange = async () => {
      const f = input.files[0];
      if (f) { await wizHandleUpload(f, "state_return", statusEl); }
    };
  } else if (wiz.step === 6) {
    body.innerHTML = `
      <div class="wiz-step" style="text-align:center;">
        <p style="font-family:var(--font-pixel);font-size:var(--fs-section);color:var(--wood-dark);margin-bottom:6px;">Processing your return</p>
        <p style="font-size:var(--fs-body-sm);color:var(--wood-dark);margin:0 0 20px;">This may take a minute — Claude is reading your documents and populating every tab.</p>
        <div class="pb-wrap">
          <div id="wiz-pb-label" class="pb-label">Starting…</div>
          <div class="pb-track">
            <div id="wiz-pb-fill" class="pb-fill"></div>
            <div id="wiz-pb-pct" class="pb-pct">0%</div>
          </div>
        </div>
      </div>`;
  }
}

function openNewYearWizard() {
  // Gather suggestion from server, then open
  fetchJSON("/api/year-suggestion").then(s => {
    wiz = {
      step: 1,
      year: s.next_suggested,
      currentFiling: s.current_filing_year,
      autoType: s.next_suggested < s.current_filing_year ? "past"
             : s.next_suggested > s.current_filing_year ? "future"
             : "current",
    };
    wiz.type = wiz.autoType;
    $("#modal").classList.remove("hidden");
    renderWizStep();
  });
}

async function wizNext() {
  if (wiz.step === 1) {
    const v = Number($("#wiz-year").value);
    if (!Number.isInteger(v) || v < 2000 || v > 2099) { alert("Enter a year between 2000 and 2099."); return; }
    if (state.yearInfo && state.yearInfo[v]) { alert(`${v} already exists.`); return; }
    wiz.year = v;
    wiz.autoType = v < wiz.currentFiling ? "past" : v > wiz.currentFiling ? "future" : "current";
    wiz.type = wiz.autoType;
    wiz.step = 2; renderWizStep(); return;
  }
  if (wiz.step === 2) { wiz.step = 3; renderWizStep(); return; }
  if (wiz.step === 3) {
    // Create year folder
    const r = await fetch("/api/year", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year: wiz.year, year_type: wiz.type }),
    });
    if (!r.ok) { alert(`Create failed: ${await r.text()}`); return; }
    const created = await r.json();
    localStorage.setItem("year", created.year);
    state.year = created.year;
    await loadYears();
    await refresh();
    // Past-year branch → continue onboarding with upload + processing
    if (wiz.type === "past") {
      wiz.step = 4; renderWizStep(); return;
    }
    wiz = null; closeModal(); return;
  }
  if (wiz.step === 4) {
    // Federal upload is required
    if (!wiz.fedUploaded) { alert("Please upload the federal return, or press Back to skip."); return; }
    wiz.step = 5; renderWizStep(); return;
  }
  if (wiz.step === 5) {
    // State upload optional (skip button exists)
    wiz.step = 6; renderWizStep(); startWizAutosync(); return;
  }
  if (wiz.step === 6) { /* processing — confirm disabled */ return; }
}

function wizBack() {
  if (!wiz || wiz.step === 1) { wiz = null; closeModal(); return; }
  if (wiz.step === 6) { return; } // no going back during processing
  wiz.step -= 1; renderWizStep();
}

// Past-year step 4/5: upload via intake, auto-commit with fixed slot prefix
async function wizHandleUpload(file, slotPrefix, statusEl) {
  statusEl.textContent = "Uploading…";
  statusEl.classList.remove("err");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch(`/api/intake?year=${wiz.year}`, { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    // Force-commit with the desired slot prefix (overrides whatever Claude picked),
    // so files get the right filename prefix for match_slot downstream.
    const commit = await fetch(`/api/commit-intake?year=${wiz.year}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        saved_path: data.saved_path,
        slot_id: slotPrefix,
        force_prefix: true,  // wizard knows the prefix it wants; bypass slot-validation
        bullets: "",
        notes: "",
        files_md_entry: data.analysis?.files_md_entry || "",
        new_open_questions: data.analysis?.new_open_questions || [],
        resolved_questions: data.analysis?.resolved_questions || [],
        quest_updates: {},
      }),
    });
    if (!commit.ok) throw new Error(await commit.text());
    statusEl.textContent = `✓ ${file.name} uploaded`;
    return true;
  } catch (e) {
    statusEl.textContent = `Failed: ${e.message}`;
    statusEl.classList.add("err");
    return false;
  }
}

async function startWizAutosync() {
  const fill = $("#wiz-pb-fill");
  const pct = $("#wiz-pb-pct");
  const label = $("#wiz-pb-label");
  const labels = ["Reading documents…", "Parsing figures…", "Updating profile…", "Computing analytics…", "Almost there…"];
  let progress = 0, labelIdx = 0;
  const tick = setInterval(() => {
    if (progress < 90) { progress += 3 + Math.random() * 4; }
    fill.style.width = Math.min(progress, 90) + "%";
    pct.textContent = Math.round(Math.min(progress, 90)) + "%";
  }, 1200);
  const labelTick = setInterval(() => {
    labelIdx = (labelIdx + 1) % labels.length;
    label.textContent = labels[labelIdx];
  }, 8000);
  label.textContent = labels[0];

  try {
    await fetch(`/api/autosync?year=${wiz.year}`, { method: "POST" });
  } catch {}
  clearInterval(tick);
  clearInterval(labelTick);
  fill.style.width = "100%";
  pct.textContent = "100%";
  label.textContent = "Done ✓";

  await new Promise(r => setTimeout(r, 600));
  wiz = null;
  closeModal();
  await loadYears();
  await refresh();
}

$("#new-year-btn").onclick = openNewYearWizard;

// ---- Ancient One (premium optimizer) ----
async function renderAncientRecs() {
  try {
    const r = await fetchJSON("/api/recommendations");
    const html = r.html || "";
    // Detect "empty state": every section only has `_none yet_` placeholders
    const parser = new DOMParser();
    const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
    const allItems = [...doc.querySelectorAll("li")];
    const real = allItems.filter(li => !/^\s*none yet/i.test(li.textContent.trim()));
    if (real.length === 0) {
      $("#ancient-recs-content").innerHTML = `
        <div class="ancient-empty-state">
          <div class="ancient-glyph">⋆ ✦ ⋆</div>
          <p>No past recommendations yet.</p>
          <p style="margin-top:10px;">Ask the Ancient One for a full review.<br>
          Findings will appear here and persist across sessions.</p>
        </div>`;
    } else {
      $("#ancient-recs-content").innerHTML = html;
    }
  } catch {
    $("#ancient-recs-content").innerHTML = `<em>Failed to load recommendations.</em>`;
  }
}

let _ancientRecsTimer = null;
function startAncientRecsPoll() {
  // Re-render recs every 3s while modal is open (catches Ancient One's writes).
  // SSE also refreshes, but a light poll is a defensive belt-and-suspenders.
  stopAncientRecsPoll();
  _ancientRecsTimer = setInterval(renderAncientRecs, 3000);
}
function stopAncientRecsPoll() {
  if (_ancientRecsTimer) { clearInterval(_ancientRecsTimer); _ancientRecsTimer = null; }
}

async function openAncient() {
  $("#ancient-modal").classList.remove("hidden");
  $("#ancient-iframe").classList.add("hidden");
  $("#ancient-loading").style.display = "block";
  renderAncientRecs();
  startAncientRecsPoll();
  const r = await fetch(`/api/optimizer/start?year=${state.year}`, { method: "POST" });
  if (!r.ok) { alert(`Failed to start Ancient One: ${await r.text()}`); closeAncient(); return; }
  for (let i = 0; i < 40; i++) {
    await new Promise(res => setTimeout(res, 300));
    const s = await fetchJSON("/api/optimizer/status");
    if (s.ready) {
      const iframe = $("#ancient-iframe");
      iframe.src = `http://127.0.0.1:${s.port}`;
      iframe.classList.remove("hidden");
      $("#ancient-loading").style.display = "none";
      return;
    }
  }
  alert("Ancient One took too long to start.");
  closeAncient();
}
function closeAncient() { $("#ancient-modal").classList.add("hidden"); stopAncientRecsPoll(); }
async function endAncient() {
  await fetch("/api/optimizer/stop", { method: "POST" });
  $("#ancient-iframe").src = "about:blank";
  closeAncient();
}
$("#ancient-btn").onclick = openAncient;
$("#ancient-close").onclick = endAncient;
$("#ancient-end").onclick = endAncient;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#ancient-modal").classList.contains("hidden")) closeAncient();
});

// Hook confirm/cancel buttons to also handle wizard mode
const _origConfirm = $("#modal-confirm").onclick;
$("#modal-confirm").onclick = async (e) => {
  if (welcome) return welcomeNext();
  if (wiz) return wizNext();
  return _origConfirm && _origConfirm(e);
};
const _origCancel = $("#modal-cancel").onclick;
$("#modal-cancel").onclick = async (e) => {
  if (welcome) return welcomeBack();
  if (wiz) return wizBack();
  return _origCancel && _origCancel(e);
};

window.openFile = openFile;

// Server-Sent Events: auto-refresh when Profile.md / Files.md / OpenQuestions.md / input/ change.
let eventSource = null;
let subscribedYear = null;
function connectEvents() {
  if (subscribedYear === state.year && eventSource && eventSource.readyState !== 2) return;
  if (eventSource) eventSource.close();
  subscribedYear = state.year;
  eventSource = new EventSource(`/api/events?year=${state.year}`);
  let pending = false;
  eventSource.addEventListener("refresh", () => {
    if (pending) return;
    pending = true;
    setTimeout(() => { pending = false; refresh(); connectEvents(); }, 200);
  });
  eventSource.onerror = () => {
    subscribedYear = null;
    setTimeout(connectEvents, 2000);
  };
}

async function bootstrap() {
  const years = await fetchJSON("/api/years");
  if (years.length === 0) {
    openWelcomeWizard();
    return;
  }
  await loadYears();
  await refresh();
  connectEvents();
}

// ---- First-run welcome: seed Global Profile + create first year ----
let welcome = null;

function openWelcomeWizard() {
  welcome = { step: 1, identity: { name: "", filing_status: "Single", residency: "", dependents: "None", citizenship: "U.S. citizen" } };
  $("#modal").classList.remove("hidden");
  renderWelcomeStep();
}

function renderWelcomeStep() {
  $("#modal").classList.remove("info-mode");
  $("#modal-title").textContent = welcome.step === 1 ? "Welcome — set up your Global Profile" : "Create your first year";
  $("#modal-confirm").textContent = welcome.step === 1 ? "Save & continue ›" : "Create year";
  $("#modal-cancel").textContent = welcome.step === 1 ? "Skip" : "‹ Back";

  const body = $("#modal-body");
  if (welcome.step === 1) {
    body.innerHTML = `
      <p style="margin:0 0 12px;font-size:var(--fs-body-sm);">
        This captures stable facts that carry across all tax years (name, filing status, residency).
        Per-year details come later. All fields optional — you can edit <code>Profile.md</code> at the root any time.
      </p>
      <div class="wiz-step">
        <label>Full name</label>
        <input id="w-name" type="text" value="${welcome.identity.name}" placeholder="e.g. Jane Doe" style="width:100%;font-family:var(--font-body);font-size:var(--fs-body);padding:8px;border:2px solid var(--wood);background:#fff8e1;">
      </div>
      <div class="wiz-step">
        <label>Filing status</label>
        <select id="w-status" style="width:100%;font-family:var(--font-body);font-size:var(--fs-body);padding:8px;border:2px solid var(--wood);background:#fff8e1;">
          ${["Single","Married filing jointly","Married filing separately","Head of household","Qualifying surviving spouse"].map(s => `<option ${s===welcome.identity.filing_status?"selected":""}>${s}</option>`).join("")}
        </select>
      </div>
      <div class="wiz-step">
        <label>Residency (state / city)</label>
        <input id="w-res" type="text" value="${welcome.identity.residency}" placeholder="e.g. NYC resident (renter), full-year" style="width:100%;font-family:var(--font-body);font-size:var(--fs-body);padding:8px;border:2px solid var(--wood);background:#fff8e1;">
      </div>
      <div class="wiz-step">
        <label>Dependents</label>
        <input id="w-deps" type="text" value="${welcome.identity.dependents}" placeholder="e.g. None" style="width:100%;font-family:var(--font-body);font-size:var(--fs-body);padding:8px;border:2px solid var(--wood);background:#fff8e1;">
      </div>`;
  } else {
    body.innerHTML = `
      <p style="margin:0 0 12px;font-size:var(--fs-body-sm);">
        Pick the first year you want to work on. The folder name is the <strong>filing year</strong>
        (the year the return is filed; it covers the prior calendar year's income).
      </p>
      <div class="wiz-step">
        <label>Filing year</label>
        <input id="w-year" type="number" min="2000" max="2099" value="${new Date().getFullYear()}" style="width:140px;font-family:var(--font-body);font-size:var(--fs-body);padding:6px 8px;border:2px solid var(--wood);background:#fff8e1;">
      </div>
      <p style="font-size:var(--fs-body-xs);color:var(--wood-dark);">We'll auto-pick the year type (past / current / future) and you can override in the next step if needed — or just use the + New Year button later.</p>`;
  }
}

async function welcomeNext() {
  if (welcome.step === 1) {
    welcome.identity.name = document.getElementById("w-name").value.trim();
    welcome.identity.filing_status = document.getElementById("w-status").value;
    welcome.identity.residency = document.getElementById("w-res").value.trim();
    welcome.identity.dependents = document.getElementById("w-deps").value.trim();
    await fetch("/api/global", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify(welcome.identity),
    });
    welcome.step = 2;
    renderWelcomeStep();
    return;
  }
  // step 2: create the first year
  const year = Number(document.getElementById("w-year").value);
  if (!Number.isInteger(year) || year < 2000 || year > 2099) { alert("Enter a valid year."); return; }
  const sug = await fetchJSON("/api/year-suggestion");
  const year_type = year < sug.current_filing_year ? "past" : year > sug.current_filing_year ? "future" : "current";
  const r = await fetch("/api/year", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ year, year_type }),
  });
  if (!r.ok) { alert("Failed to create year: " + await r.text()); return; }
  welcome = null;
  closeModal();
  await loadYears();
  await refresh();
  connectEvents();
}

function welcomeBack() {
  if (welcome.step === 1) { welcome = null; closeModal(); return; }
  welcome.step -= 1;
  renderWelcomeStep();
}

// ---- Wizard's Tower: tab management ----
// One iframe per tab is kept mounted in #terminal-frames. Switching tabs just
// toggles the .active class so the browser never unloads a session (avoids the
// "are you sure you want to leave?" prompt and preserves scrollback).
function setActiveTab(tabEl) {
  document.querySelectorAll(".wizard-tab").forEach(t => t.classList.remove("active"));
  tabEl.classList.add("active");
  const tabId = tabEl.dataset.tabId;
  document.querySelectorAll(".wizard-frame").forEach(f => {
    f.classList.toggle("active", f.dataset.tabId === tabId);
  });
}

function ensureWizardFrame(tabId, port) {
  let frame = document.querySelector(`.wizard-frame[data-tab-id="${tabId}"]`);
  if (!frame) {
    frame = document.createElement("iframe");
    frame.className = "wizard-frame";
    frame.dataset.tabId = tabId;
    frame.src = `http://127.0.0.1:${port}`;
    $("#terminal-frames").appendChild(frame);
  }
  return frame;
}

function addTabElement({ tab_id, port, name }) {
  const tabs = $("#wizard-tabs");
  const btn = document.createElement("button");
  btn.className = "wizard-tab";
  btn.dataset.port = port;
  btn.dataset.name = name;
  btn.dataset.tabId = tab_id;
  btn.innerHTML = `🧙 ${name}<span class="tab-close" title="Close session">✕</span>`;
  btn.onclick = (e) => {
    if (e.target.classList.contains("tab-close")) return;
    setActiveTab(btn);
  };
  btn.querySelector(".tab-close").onclick = async (e) => {
    e.stopPropagation();
    await fetch(`/api/wizard/tab?id=${tab_id}`, { method: "DELETE" });
    const wasActive = btn.classList.contains("active");
    const frame = document.querySelector(`.wizard-frame[data-tab-id="${tab_id}"]`);
    if (frame) frame.remove();
    btn.remove();
    if (wasActive) setActiveTab(document.querySelector('.wizard-tab[data-tab-id="merlin"]'));
  };
  tabs.appendChild(btn);
  ensureWizardFrame(tab_id, port);
  return btn;
}

async function startWizardTab(topic) {
  const r = await fetch("/api/wizard/tab", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, year: state.year }),
  });
  if (!r.ok) { alert("Failed to start wizard: " + await r.text()); return; }
  const data = await r.json();
  const btn = addTabElement(data);
  setActiveTab(btn);
  closeModal();
}

// Merlin tab wiring + restore any existing tabs on page load
(function initWizardTabs() {
  const merlin = document.querySelector('.wizard-tab[data-tab-id="merlin"]');
  merlin.onclick = () => setActiveTab(merlin);
  fetchJSON("/api/wizard/tabs").then(tabs => {
    tabs.forEach(addTabElement);
  }).catch(() => {});
})();

// Draggable horizontal splitter between Inspect and Wizard's Tower.
// Uses DELTA-based positioning (anchors at pointerdown, not to the pointer's
// absolute Y) so the splitter moves relative to where you grabbed it, like
// every native OS splitter. Listens on document for move/up events so the
// drag survives even if the cursor leaves the button mid-drag.
(function initSplitter() {
  const splitter = document.getElementById("middle-splitter");
  const col = document.getElementById("middle-col");
  if (!splitter || !col) return;

  const MIN_H = 120;
  const maxHeightForViewport = () => Math.max(MIN_H + 1, window.innerHeight - 200);

  const saved = Number(localStorage.getItem("wizardPaneHeight"));
  if (Number.isFinite(saved) && saved >= MIN_H && saved <= maxHeightForViewport()) {
    col.style.setProperty("--wizard-height", saved + "px");
  } else if (saved && (saved < MIN_H || saved > maxHeightForViewport())) {
    localStorage.removeItem("wizardPaneHeight");
  }

  // Drag state: captured on pointerdown, read on every pointermove.
  let dragging = false;
  let startY = 0;
  let startH = 0;
  let pointerId = null;
  let rafId = 0;
  let pendingH = 0;

  const currentWizardH = () => {
    const v = col.style.getPropertyValue("--wizard-height").trim();
    return v ? parseFloat(v) : 300;
  };

  const onMove = (e) => {
    if (!dragging) return;
    // Moving the pointer UP (clientY decreases) should GROW the terminal.
    const deltaY = e.clientY - startY;
    let h = startH - deltaY;
    h = Math.max(MIN_H, Math.min(maxHeightForViewport(), h));
    pendingH = h;
    if (!rafId) {
      rafId = requestAnimationFrame(() => {
        col.style.setProperty("--wizard-height", pendingH + "px");
        rafId = 0;
      });
    }
  };

  const onUp = (e) => {
    if (!dragging) return;
    dragging = false;
    try { splitter.releasePointerCapture(pointerId); } catch {}
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    document.removeEventListener("pointercancel", onUp);
    splitter.classList.remove("dragging");
    document.body.style.userSelect = "";
    localStorage.setItem("wizardPaneHeight", String(currentWizardH()));
  };

  splitter.addEventListener("pointerdown", (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    dragging = true;
    pointerId = e.pointerId;
    startY = e.clientY;
    startH = currentWizardH();
    try { splitter.setPointerCapture(e.pointerId); } catch {}
    splitter.classList.add("dragging");
    document.body.style.userSelect = "none";
    // Listen on document so we don't lose the drag if the cursor leaves the splitter.
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", onUp);
    e.preventDefault();
  });

  // Keyboard accessibility: ↑/↓ nudge when splitter is focused.
  splitter.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const step = e.shiftKey ? 40 : 10;
    const next = Math.max(MIN_H, Math.min(maxHeightForViewport(),
      currentWizardH() + (e.key === "ArrowUp" ? step : -step)));
    col.style.setProperty("--wizard-height", next + "px");
    localStorage.setItem("wizardPaneHeight", String(next));
  });
})();

bootstrap();

// Hook into year-tab changes to re-subscribe.
const _origRefresh = refresh;
refresh = async function () { await _origRefresh(); if (subscribedYear !== state.year) connectEvents(); };
