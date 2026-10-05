/* Bindery web client — vanilla JS, no dependencies.
   Display order = merge order. Drag-sort uses pointer events + FLIP so
   rows glide live while a floating ghost follows the cursor. */
"use strict";

const state = { session: null, files: [], selectedId: null, selPage: 0, merged: false,
                limits: { max_file_mb: 50, max_files: 30, session_max_mb: 200 },
                finalView: null };

const $ = (id) => document.getElementById(id);
const listEl = $("fileList"), emptyEl = $("emptyState");

const svg = (path) =>
  `<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" ` +
  `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
  `<path d="${path}"/></svg>`;
const I = {
  up: svg("M8 13V3M3.5 7.5L8 3l4.5 4.5"),
  down: svg("M8 3v10M3.5 8.5L8 13l4.5-4.5"),
  x: svg("M4 4l8 8M12 4l-8 8"),
  check: `<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>`,
  dl: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 2.5v8m0 0L5 7.5m3 3l3-3M3 13.5h10"/></svg>`,
};

const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtSize = (b) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB`
  : `${(b / 1048576).toFixed(1)} MB`;
const thumb = (id, page, zoom) =>
  `/api/preview?session_id=${state.session}&file_id=${id}&page=${page}&zoom=${zoom}`;

function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("toasts").appendChild(t);
  setTimeout(() => t.remove(), 5200);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Free-tier servers sleep and temp files die on restarts: retry the
// wake-up window, and heal a lost session instead of erroring out.
const WAKE_DELAYS = [2000, 5000, 10000, 20000, 30000];
const isSessionGone = (j) =>
  !!j && j.ok === false && /session expired|unknown/i.test(j.error || "");

async function req(url, opts = {}) {
  let woke = false;
  for (let attempt = 0; ; attempt++) {
    let r;
    try {
      r = await fetch(url, opts);
    } catch {
      if (attempt >= WAKE_DELAYS.length)
        throw new Error("Can't reach the server. It may be waking up — wait a minute and try again.");
      if (!woke) { woke = true; toast("Waking the server, one moment…"); }
      await sleep(WAKE_DELAYS[attempt]);
      continue;
    }
    if ((r.status === 502 || r.status === 503 || r.status === 504) && attempt < WAKE_DELAYS.length) {
      if (!woke) { woke = true; toast("Waking the server, one moment…"); }
      await sleep(WAKE_DELAYS[attempt]);
      continue;
    }
    if (r.status === 413) throw new Error("Those files are too large for this server.");
    let j = null;
    try { j = await r.json(); } catch { /* non-JSON body */ }
    if (isSessionGone(j)) {
      await recoverSession();
      const e = new Error("__recovered__");
      e.recovered = true;
      throw e;
    }
    if (!r.ok) throw new Error((j && j.error) || `Request failed (${r.status}).`);
    return j;
  }
}

async function recoverSession() {
  // Server restarted / slept: temp uploads are gone for good. Grab a
  // fresh session, clear the (now phantom) list, and say so plainly.
  try {
    const j = await (await fetch("/api/session", { method: "POST" })).json();
    state.session = j.session_id;
    if (j.limits) { state.limits = j.limits; renderLimits(); }
  } catch { /* next call will retry/recover again */ }
  state.files = []; state.selectedId = null; state.selPage = 0;
  refreshAll();
  toast("The server restarted and lost your uploads — please add your files again.");
}

function setStep() {
  const s = state.files.length ? (state.merged ? 3 : 2) : 1;
  document.querySelectorAll(".step").forEach((el) => {
    const n = +el.dataset.n;
    el.classList.toggle("active", n === s);
    el.classList.toggle("done", n < s);
  });
}

/* ---------------- session + upload ---------------- */
async function init() {
  try {
    const s = await req("/api/session", { method: "POST" });
    state.session = s.session_id;
    if (s.limits) state.limits = s.limits;
    renderLimits();
  } catch (err) {
    if (!err.recovered) toast("Could not reach the server. Is it running?", true);
  }
  wireTabs();
  wireLightbox();
  $("fileInput").addEventListener("change", (e) => {
    uploadFiles(e.target.files);
    e.target.value = "";
  });
  $("clearBtn").addEventListener("click", clearAll);
  $("mergeBtn").addEventListener("click", doMerge);
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
  });
  refreshAll();
}

function renderLimits() {
  const el = $("limitsNote");
  const { max_file_mb, max_files } = state.limits;
  el.innerHTML = `Heads-up: max <b>${max_file_mb} MB</b> per file · up to <b>${max_files}</b> files per batch.`;
  el.hidden = false;
}

async function uploadFiles(fileList) {
  if (!state.session) return toast("No session yet — reload the page.", true);
  const pdfs = [...fileList].filter((f) => /\.(pdf|docx?|pptx?|odt|odp|rtf|txt)$/i.test(f.name));
  if (!pdfs.length) return toast("Only PDF, Word or PowerPoint files, please.", true);
  // instant client-side size gate — no waiting for a doomed upload
  const cap = state.limits.max_file_mb * 1048576;
  const okFiles = [];
  pdfs.forEach((f) => {
    if (f.size > cap) toast(`${f.name} skipped: ${fmtSize(f.size)} is over the ${state.limits.max_file_mb} MB per-file limit.`, true);
    else okFiles.push(f);
  });
  if (!okFiles.length) return;
  const fd = new FormData();
  fd.append("session_id", state.session);
  okFiles.forEach((f) => fd.append("files", f, f.name));
  setBusy(true);
  try {
    const j = await req("/api/upload", { method: "POST", body: fd });
    if (!j.ok) throw new Error(j.error || "Upload failed.");
    (j.added || []).forEach((f) => state.files.push(f));
    (j.rejected || []).forEach((x) => toast(`${x.name} skipped: ${x.reason}`, true));
    if (j.added?.length) {
      if (!state.selectedId) { state.selectedId = j.added[0].id; state.selPage = 0; }
      toast(`${j.added.length} file${j.added.length === 1 ? "" : "s"} added to the end — drag to reorder.`);
    }
  } catch (err) {
    if (!err.recovered) toast(String(err.message || err), true);
  } finally {
    setBusy(false);
    refreshAll();
  }
}

async function clearAll() {
  if (!state.files.length) return;
  if (!confirm(`Remove all ${state.files.length} files from the queue?`)) return;
  try { await fetch(`/api/session/${state.session}`, { method: "DELETE" }); } catch { /* ignore */ }
  state.files = []; state.selectedId = null; state.selPage = 0;
  try {
    const s = await req("/api/session", { method: "POST" });
    state.session = s.session_id;
    if (s.limits) { state.limits = s.limits; renderLimits(); }
  } catch (err) {
    if (!err.recovered) toast(String(err.message || err), true);
  }
  refreshAll();
}

async function removeFile(id) {
  state.files = state.files.filter((f) => f.id !== id);
  if (state.selectedId === id) {
    state.selectedId = state.files[0]?.id ?? null;
    state.selPage = 0;
  }
  fetch(`/api/file?session_id=${state.session}&file_id=${id}`, { method: "DELETE" }).catch(() => {});
  refreshAll();
}

/* ---------------- order manager ---------------- */
function moveFile(idx, dir) {
  const j = idx + dir;
  if (j < 0 || j >= state.files.length) return;
  [state.files[idx], state.files[j]] = [state.files[j], state.files[idx]];
  state.selectedId = state.files[j].id;
  refreshAll();
}

function renderList() {
  listEl.innerHTML = "";
  emptyEl.style.display = state.files.length ? "none" : "";
  state.files.forEach((f, i) => {
    const card = document.createElement("div");
    card.className = "file-card" + (f.id === state.selectedId ? " selected" : "");
    card.dataset.id = f.id;
    const meta = f.converted
      ? `${f.pages} pages · ${fmtSize(f.size)} · converted from ${esc(f.converted)}`
      : `${f.pages} pages · ${fmtSize(f.size)}`;
    card.innerHTML =
      `<span class="grip" title="Hold and drag to move">⋮⋮</span>` +
      `<span class="badge">${i + 1}</span>` +
      `<span class="txt"><span class="name">${esc(f.name)}</span><br>` +
      `<span class="meta">${meta}</span></span>` +
      `<button class="tool" data-act="up" title="Move up" aria-label="Move up">${I.up}</button>` +
      `<button class="tool" data-act="down" title="Move down" aria-label="Move down">${I.down}</button>` +
      `<button class="tool" data-act="rm" title="Remove" aria-label="Remove">${I.x}</button>`;
    card.querySelector('[data-act="up"]').onclick = () => moveFile(i, -1);
    card.querySelector('[data-act="down"]').onclick = () => moveFile(i, +1);
    card.querySelector('[data-act="rm"]').onclick = () => removeFile(f.id);
    card.addEventListener("pointerdown", onCardPress);
    listEl.appendChild(card);
  });
  $("mergeBtn").disabled = !state.files.length;
}

/* Lively pointer drag-sort with FLIP glide.
   Tap (press + release, no drag) selects from anywhere on the card.
   Dragging starts anywhere with a mouse, but only from the grip on
   touch — otherwise the page could never scroll. */
let drag = null;
function onCardPress(e) {
  if (e.button !== 0 && e.pointerType === "mouse") return;
  if (e.target.closest("button")) return;
  const card = e.currentTarget;
  drag = { card, x0: e.clientX, y0: e.clientY, live: false, gap: null,
           canDrag: e.pointerType === "mouse" || !!e.target.closest(".grip") };
  card.addEventListener("pointermove", onCardMove);
  card.addEventListener("pointerup", onCardDrop, { once: true });
  card.addEventListener("pointercancel", onCardCancel, { once: true });
}

function onCardCancel() {
  // e.g. the browser took over for scrolling: select/settle nothing
  const d = drag;
  drag = null;
  document.body.style.cursor = "";
  if (!d) return;
  d.card.removeEventListener("pointermove", onCardMove);
  if (!d.live) return;
  if (d.gap) d.gap.remove();
  d.card.classList.remove("floating");
  d.card.style.cssText = "";
}

function onCardMove(e) {
  if (!drag) return;
  if (drag.live) { moveFloat(e.clientY); return; }
  if (!drag.canDrag) return; // touch outside the grip: let the page scroll
  if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 8) return;
  startFloat(e);
}

function startFloat(e) {
  const { card } = drag;
  const r = card.getBoundingClientRect();
  drag.live = true;
  drag.offY = e.clientY - r.top;
  drag.cardH = r.height;
  try { card.setPointerCapture(e.pointerId); } catch { /* ignore */ }
  card.classList.add("floating");
  Object.assign(card.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px" });
  const gap = document.createElement("div");
  gap.className = "file-gap";
  gap.style.height = "0px";
  card.after(gap);
  requestAnimationFrame(() => { gap.style.height = drag.cardH + "px"; });
  drag.gap = gap;
  document.body.style.cursor = "grabbing";
  moveFloat(e.clientY);
}

function siblings(except) {
  return [...listEl.querySelectorAll(".file-card")].filter((c) => c !== except);
}

function moveFloat(clientY) {
  const { card, gap } = drag;
  card.style.top = clientY - drag.offY + "px";
  const others = siblings(card);
  const target = others.find((c) => {
    const r = c.getBoundingClientRect();
    return clientY < r.top + r.height / 2;
  });
  // FLIP: snapshot tops, move gap, invert the shift, let it glide back
  const first = new Map(others.map((c) => [c, c.getBoundingClientRect().top]));
  if (target) listEl.insertBefore(gap, target);
  else listEl.appendChild(gap);
  others.forEach((c) => {
    const dy = first.get(c) - c.getBoundingClientRect().top;
    if (dy) {
      c.style.transform = `translateY(${dy}px)`;
      requestAnimationFrame(() => { c.style.transform = ""; });
    }
  });
}

function onCardDrop(e) {
  const d = drag;
  drag = null;
  document.body.style.cursor = "";
  if (!d) return;
  d.card.removeEventListener("pointermove", onCardMove);
  if (!d.live) { selectFile(d.card.dataset.id); return; } // plain tap = select
  e?.preventDefault?.();
  const { card, gap } = d;
  // settle card into the gap slot
  listEl.insertBefore(card, gap);
  gap.remove();
  card.classList.remove("floating");
  card.style.cssText = "";
  card.classList.add("dropped");
  setTimeout(() => card.classList.remove("dropped"), 400);
  // commit DOM order → state order (badges updated in place: no rebuild flash)
  const order = [...listEl.querySelectorAll(".file-card")].map((c) => c.dataset.id);
  const byId = new Map(state.files.map((f) => [f.id, f]));
  state.files = order.map((id) => byId.get(id)).filter(Boolean);
  [...listEl.querySelectorAll(".file-card .badge")].forEach((b, i) => {
    b.textContent = `${i + 1}`;
  });
  hideResult();
  updateTotals();
  renderMerged();
}

function selectFile(id) {
  if (state.selectedId !== id) state.selPage = 0;
  state.selectedId = id;
  listEl.querySelectorAll(".file-card").forEach((c) =>
    c.classList.toggle("selected", c.dataset.id === id));
  renderSelected();
}

/* ---------------- previews ---------------- */
function updateTotals() {
  const n = state.files.length;
  const pages = state.files.reduce((s, f) => s + f.pages, 0);
  $("totals").textContent = `${n} file${n === 1 ? "" : "s"} · ${pages} page${pages === 1 ? "" : "s"}`;
}

function currentFile() {
  return state.files.find((f) => f.id === state.selectedId) ?? null;
}

function renderSelected() {
  const f = currentFile();
  if (!f) {
    $("selTitle").textContent = state.files.length ? "Pick a file to inspect it" : "Nothing selected";
    $("selMeta").textContent = "";
    $("selHero").textContent = "Click a file in the queue to inspect its pages.";
    $("selPager").innerHTML = "";
    $("selStrip").innerHTML = "";
    return;
  }
  const pos = state.files.indexOf(f) + 1;
  const page = Math.min(state.selPage, f.pages - 1);
  state.selPage = page;
  $("selTitle").textContent = `#${pos} — ${f.name}`;
  $("selMeta").textContent = `Position ${pos} of ${state.files.length} · ${f.pages} pages · ${fmtSize(f.size)}`;
  $("selHero").innerHTML = `<img src="${thumb(f.id, page, 1.3)}" alt="Page ${page + 1} of ${esc(f.name)}" title="Click to view fullscreen">`;
  const heroImg = $("selHero").querySelector("img");
  if (heroImg) heroImg.onclick = openLightbox;
  $("selPager").innerHTML = f.pages > 1
    ? `<div class="pager"><button class="pbtn" id="pgPrev" type="button" aria-label="Previous page" ${page === 0 ? "disabled" : ""}>‹</button>` +
      `<span>Page ${page + 1} of ${f.pages}</span>` +
      `<button class="pbtn" id="pgNext" type="button" aria-label="Next page" ${page === f.pages - 1 ? "disabled" : ""}>›</button></div>`
    : "";
  const prev = $("pgPrev"), next = $("pgNext");
  if (prev) prev.onclick = () => stepPage(-1);
  if (next) next.onclick = () => stepPage(+1);
  const strip = $("selStrip");
  strip.innerHTML = Array.from({ length: f.pages }, (_, p) =>
    `<figure><img loading="lazy" src="${thumb(f.id, p, 0.7)}" alt="Page ${p + 1}" data-p="${p}"` +
    (p === page ? ` class="active"` : "") + `><figcaption>p. ${p + 1}</figcaption></figure>`).join("");
  strip.querySelectorAll("img").forEach((img) => {
    img.onclick = () => { state.selPage = +img.dataset.p; renderSelected(); };
  });
}

function stepPage(d) {
  const f = currentFile();
  if (!f) return;
  state.selPage = Math.min(f.pages - 1, Math.max(0, state.selPage + d));
  renderSelected();
}

function renderMerged() {
  const box = $("mergedSections");
  if (!state.files.length) {
    $("mergedSummary").textContent =
      "Your bound preview lands here — add files and arrange them top to bottom.";
    box.innerHTML = "";
    return;
  }
  const total = state.files.reduce((s, f) => s + f.pages, 0);
  $("mergedSummary").textContent =
    `${state.files.length} files, ${total} pages, in this exact order. ` +
    `What you see below is what the bound file will hold.`;
  let run = 0;
  box.innerHTML = state.files.map((f, i) => {
    const start = run + 1;
    run += f.pages;
    const thumbs = Array.from({ length: f.pages }, (_, p) =>
      `<figure><img loading="lazy" src="${thumb(f.id, p, 0.7)}" alt="">` +
      `<figcaption>p. ${start + p}</figcaption></figure>`).join("");
    return `<div class="msec"><div class="head"><span class="badge">${i + 1}</span>` +
      `<span class="t">${esc(f.name)}<small>becomes pages ${start}–${run} · ${f.pages} pages</small></span></div>` +
      `<div class="thumbs">${thumbs}</div></div>` +
      (i < state.files.length - 1 ? `<div class="marrow">then</div>` : "");
  }).join("");
}

/* ---------------- merge ---------------- */
function setBusy(b) {
  $("progress").hidden = !b;
  $("mergeBtn").disabled = b || !state.files.length;
  $("mergeLabel").textContent = b ? "Binding…" : "Bind PDF";
}
function hideResult() {
  state.merged = false;
  state.finalView = null;
  $("result").hidden = true;
  $("result").innerHTML = "";
  setStep();
}

async function doMerge() {
  if (!state.files.length) return;
  setBusy(true);
  hideResult();
  try {
    const j = await req("/api/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.session,
        order: state.files.map((f) => f.id),
        filename: $("outName").value.trim() || "merged_document.pdf",
      }),
    });
    if (!j.ok) throw new Error(j.error || "Merge failed.");
    const rows = j.page_map.map((m) =>
      `<tr><td>No. ${m.position}</td><td>${esc(m.name)}</td><td>pages ${m.start}–${m.end}</td></tr>`).join("");
    const box = $("result");
    box.innerHTML =
      `<div class="stamp-row"><span class="stamp">BOUND</span>` +
      `<h3>${j.files} files, ${j.pages} pages — in your order</h3></div>` +
      `<table>${rows}</table>` +
      `<p class="fine">Checked: output pages equal the sum of the inputs, sequence untouched.</p>` +
      `<a class="dl" href="${j.download_url}" download="${esc(j.filename)}">${I.dl} Download ${esc(j.filename)}</a>` +
      `<button class="dl ghostbtn" id="previewFinal" type="button">Preview the final document</button>`;
    box.hidden = false;
    state.merged = true;
    state.finalView = { token: j.token, pages: j.pages };
    setStep();
    $("previewFinal").onclick = openFinalPreview;
    toast(`Bound ${j.files} files into ${j.pages} pages.`);
  } catch (err) {
    if (!err.recovered) toast(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
}

/* ---------------- fullscreen lightbox (file page OR final document) ---------------- */
function openLightbox() {
  if (!currentFile()) return;
  state.finalView = null; // hero views always show the selected file's page
  $("lightbox").hidden = false;
  document.body.style.overflow = "hidden";
  renderLightbox();
}
function openFinalPreview() {
  if (!state.finalView) return;
  state.finalPage = 0;
  $("lightbox").hidden = false;
  document.body.style.overflow = "hidden";
  renderLightbox();
}
function closeLightbox() {
  $("lightbox").hidden = true;
  document.body.style.overflow = "";
}
function lbStep(d) {
  // one navigator for both modes; hero pager stays in sync in file mode
  if (state.finalView) {
    state.finalPage = Math.min(state.finalView.pages - 1,
      Math.max(0, (state.finalPage || 0) + d));
  } else {
    stepPage(d);
  }
  renderLightbox();
}
function renderLightbox() {
  if (state.finalView) {
    // rendered from the ACTUAL generated file — exactly what download holds
    const p = state.finalPage || 0;
    const img = $("lbImg");
    img.src = `/api/preview?session_id=${state.session}&token=${state.finalView.token}&page=${p}&zoom=2.0`;
    img.alt = `Final document, page ${p + 1}`;
    $("lbCap").textContent = `Final document — page ${p + 1} of ${state.finalView.pages}`;
    $("lbPrev").disabled = p === 0;
    $("lbNext").disabled = p === state.finalView.pages - 1;
    return;
  }
  const f = currentFile();
  if (!f) return closeLightbox();
  const img = $("lbImg");
  img.src = thumb(f.id, state.selPage, 2.0);
  img.alt = `Page ${state.selPage + 1} of ${f.name}`;
  $("lbCap").textContent = `${f.name} — page ${state.selPage + 1} of ${f.pages}`;
  $("lbPrev").disabled = state.selPage === 0;
  $("lbNext").disabled = state.selPage === f.pages - 1;
}
function wireLightbox() {
  $("lbClose").onclick = closeLightbox;
  $("lbPrev").onclick = () => lbStep(-1);
  $("lbNext").onclick = () => lbStep(+1);
  $("lightbox").addEventListener("click", (e) => {
    if (e.target === $("lightbox")) closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if ($("lightbox").hidden) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") lbStep(-1);
    else if (e.key === "ArrowRight") lbStep(+1);
  });
}

/* ---------------- misc ---------------- */
function wireTabs() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      $("tab-sel").hidden = t.dataset.tab !== "sel";
      $("tab-merged").hidden = t.dataset.tab !== "merged";
    };
  });
}

function refreshAll() {
  closeLightbox();
  renderList();
  updateTotals();
  renderSelected();
  renderMerged();
  hideResult();
}

init();
