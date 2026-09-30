/* Grounded – front end. Vanilla JS, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const pct = (x) => Math.round(x * 100);

const state = { result: null, evidenceById: {}, meta: null, people: [], peopleById: {} };

const STATUS = {
  answered: ["ok", "Answered"],
  contested: ["warn", "Conflict flagged"],
  informal: ["warn", "Informal source"],
  partial: ["warn", "Weak evidence"],
  missing: ["bad", "No evidence"],
};
const EYE = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>`;
const PROGRESS = ["Resolving context", "Planning sub-questions", "Searching passages", "Scoring trust", "Checking conflicts", "Consolidating"];

async function init() {
  const [people, suggestions, health, meta] = await Promise.all([
    fetch("/api/people").then((r) => r.json()),
    fetch("/api/suggestions").then((r) => r.json()),
    fetch("/api/health").then((r) => r.json()),
    fetch("/api/meta").then((r) => r.json()),
  ]);
  state.people = people; state.meta = meta;
  $("#user").innerHTML = `<option value="">anonymous</option>` + people.filter((p) => p.active).map((p) => `<option value="${p.id}">${esc(p.name)} · ${esc(p.team)}</option>`).join("");
  state.health = health;
  $("#suggestions").innerHTML = suggestions.map((s, i) => `<button class="chip ${i >= 3 ? "extra" : ""}" type="button">${esc(s)}</button>`).join("");
  $("#morelink").addEventListener("click", () => { $("#suggestions").classList.add("show-all"); $("#morelink").classList.add("hidden"); });
  $("#evtoggle").addEventListener("click", () => $("#evidence-card").classList.toggle("collapsed"));

  $("#suggestions").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (b) { $("#q").value = b.textContent; ask(); } });
  $("#askform").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
  $("#addbtn").addEventListener("click", openAddKnowledge);
  $("#copybtn").addEventListener("click", copyAnswer);
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  document.addEventListener("click", (e) => {
    const go = e.target.closest(".gotab");
    if (go) { e.preventDefault(); switchTab(go.dataset.tab); return; }
    const act = e.target.closest("[data-action]");
    if (act) { reviewAction(act); return; }
    const person = e.target.closest("[data-person]");
    if (person) { openPerson(person.dataset.person); return; }
    const cite = e.target.closest("[data-ev]");
    if (cite) { openEvidence(cite.dataset.ev); return; }
    const doc = e.target.closest("[data-doc]");
    if (doc) { openDocument(doc.dataset.doc, doc.dataset.from, doc.dataset.to); return; }
    if (e.target.closest(".modal-backdrop") || e.target.closest("[data-close]")) closeOverlays();
  });
  document.addEventListener("mouseover", (e) => {
    const cite = e.target.closest(".cite");
    document.querySelectorAll(".evidence-item.flash").forEach((x) => x.classList.remove("flash"));
    if (cite) { const card = document.querySelector(`.evidence-item[data-ev="${cite.dataset.ev}"]`); if (card) card.classList.add("flash"); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeOverlays(); });

  const params = new URLSearchParams(location.search);
  if (params.get("q")) { $("#q").value = params.get("q"); await ask(); if (params.get("tab")) switchTab(params.get("tab")); if (params.get("ev")) openEvidence(params.get("ev")); }
  if (params.get("panel") === "sources") openAddKnowledge("sources");
}

function updateHealth(h) { state.health = h; }

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${name}`));
}

function showProgress() {
  $("#tab-answer").innerHTML = `<ul class="progress">${PROGRESS.map((s, i) => `<li class="${i === 0 ? "active" : ""}"><span class="dot"></span>${s}</li>`).join("")}</ul>`;
  let i = 0;
  return setInterval(() => {
    const items = document.querySelectorAll("#tab-answer .progress li");
    if (!items.length || i >= items.length - 1) return;
    items[i].classList.remove("active"); items[i].classList.add("done"); items[i].querySelector(".dot").textContent = "✓";
    i++; items[i].classList.add("active");
  }, 220);
}

async function ask() {
  const q = $("#q").value.trim();
  if (!q) return;
  $("#askbtn").disabled = true; $("#askbtn").textContent = "Thinking…";
  $("#hero").classList.add("compact");
  $("#results").classList.remove("hidden");
  const timer = showProgress();
  const started = Date.now();
  try {
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, user_id: $("#user").value || null }) });
    const result = await r.json();
    await new Promise((res) => setTimeout(res, Math.max(0, 900 - (Date.now() - started))));  // let the progress finish gracefully
    state.result = result;
    state.evidenceById = Object.fromEntries(result.evidence.map((e) => [e.id, e]));
    for (const c of result.review.conflicts) { state.evidenceById[c.kept.id] = c.kept; state.evidenceById[c.rejected.id] = c.rejected; }
    for (const d of result.review.duplicates) { state.evidenceById[d.kept.id] = d.kept; state.evidenceById[d.duplicate.id] = d.duplicate; }
    for (const o of result.review.outdated) state.evidenceById[o.item.id] = o.item;
    for (const o of result.review.out_of_scope) state.evidenceById[o.item.id] = o.item;
    render(result);
    switchTab("answer");
    history.replaceState(null, "", `?q=${encodeURIComponent(q)}`);
  } catch (err) {
    $("#tab-answer").innerHTML = `<div class="note gap">Something went wrong: ${esc(err.message)}</div>`;
  } finally {
    clearInterval(timer);
    $("#askbtn").disabled = false; $("#askbtn").textContent = "Ask";
  }
}

function render(r) {
  renderAnswer(r); renderEvidence(r); renderReview(r); renderTrace(r); renderExperts(r);
}

function citeChip(id) {
  const e = state.evidenceById[id];
  return `<span class="cite ${e && e.contested ? "contested" : ""}" data-ev="${id}" title="${esc(e ? e.title : id)}">${id}</span>`;
}

function verdictClass(r) {
  if (r.confidence === 0) return "bad";
  if (r.verdict === "Grounded answer") return "ok";
  return "warn";
}

function refLine(seg, label) {
  const e = state.evidenceById[seg.evidence[0]];
  if (!e) return "";
  const who = e.owner || e.author;
  return `<div class="ref"><span class="kicker">${label}</span>${esc(e.title)}<span class="muted"> · ${who ? esc(who) + " · " : ""}${fmtDate(e.updated_at)}</span>${citeChip(e.id)}</div>`;
}

function renderAnswer(r) {
  const c = r.context;
  const vc = verdictClass(r);
  const meterClass = r.confidence >= 0.7 ? "" : r.confidence >= 0.4 ? "mid" : "low";
  const single = r.sections.length === 1;
  let html = `
    <div class="verdict">
      <span class="badge ${vc}">${vc === "ok" ? "✓" : vc === "bad" ? "!" : "⚠"} ${esc(r.verdict)}</span>
      <div class="meter ${meterClass}"><div class="bar"><i style="width:${pct(r.confidence)}%"></i></div><span>${pct(r.confidence)}%</span></div>
      <span class="scope" title="${esc(c.country_source || "")}">${esc(c.country_name || "All countries")}${c.client ? ` · ${esc(c.client)}` : ""}${c.team ? ` · ${esc(c.team)}` : ""}</span>
    </div>`;

  for (const s of r.sections) {
    const [cls, label] = STATUS[s.status] || ["grey", s.status];
    html += `<div class="section">`;
    if (!single) html += `<div class="section-head"><span class="badge grey">${esc(s.id)}</span><h4>${esc(s.question)}</h4><span class="badge ${cls}">${label}</span></div>`;
    const refs = [];
    for (const seg of s.segments) {
      if (seg.kind === "primary") {
        html += `<p class="lead">${esc(seg.lead || seg.text)}${seg.evidence.map(citeChip).join("")}</p>`;
        if (seg.rest) html += `<p class="detail">${esc(seg.rest)}</p>`;
      } else if (seg.kind === "weak") {
        html += `<p class="answer-text weak"><span class="kicker">Closest match</span>${esc(seg.text)}${seg.evidence.map(citeChip).join("")}</p>`;
      } else {
        refs.push(refLine(seg, seg.kind === "confirms" ? "Confirmed by" : seg.kind === "earlier" ? "Earlier" : "Related"));
      }
    }
    if (refs.length) html += `<div class="refs">${refs.join("")}</div>`;
    const bits = [];
    if (s.note && s.status !== "missing") bits.push(esc(s.note.replace("; see the review tab.", ".").replace(" The people below are the most likely to know.", "").replace(" Confirm with the people below.", "")) + (s.status === "contested" ? ` <a href="#" class="gotab" data-tab="review">Resolve it →</a>` : ""));
    if (s.experts && s.experts.length && s.status !== "missing" && s.status !== "partial") {
      bits.push(`Confirm with ${s.experts.slice(0, 2).map((p) => `<b>${esc(p.name)}</b>`).join(" or ")}.`);
    }
    if (bits.length) html += `<div class="note ${s.status === "missing" ? "gap" : s.status === "contested" ? "warn" : ""}">${bits.join(" ")}</div>`;
    if (s.status === "missing") {
      html += `<p class="lead muted-lead">No grounded answer in the knowledge base${c.country_name ? ` for ${esc(c.country_name)}` : ""}.</p><p class="detail">Nothing is claimed without evidence. The people listed alongside are the most likely to know, ranked by their track record on this topic.</p>`;
    }
    html += `</div>`;
  }
  $("#tab-answer").innerHTML = html;
}

function personCard(p, action = "") {
  state.peopleById[p.id] = p;
  return `<div class="person">
    <div class="avatar">${esc(p.initials)}</div>
    <div class="person-body">
      <div class="person-top"><span class="name">${esc(p.name)}</span><span class="score">${p.score}</span></div>
      <div class="role">${esc(p.role)}</div>
      ${p.reasons.length ? `<div class="why">${esc(p.reasons[0])}</div>` : ""}
    </div>
    <div class="person-actions">${action}<button class="eye small" type="button" data-person="${esc(p.id)}" title="How this score is built">${EYE}</button></div>
  </div>`;
}

function openPerson(id) {
  const p = state.peopleById[id];
  if (!p) return;
  const r = state.result;
  const subject = encodeURIComponent(`Question: ${r.question}`);
  $("#modal-body").innerHTML = `
    <button class="close" data-close>✕</button>
    <div class="person-head"><div class="avatar big">${esc(p.initials)}</div><div><h3 style="margin:0">${esc(p.name)}</h3><div class="sub" style="margin:2px 0 0">${esc(p.role)} · ${esc(p.team)}${p.country ? " · " + esc(p.country) : ""} · ${p.seniority_years} yrs</div></div></div>
    <div class="confrow" style="margin-top:16px"><b>Credibility ${p.score} / 100</b><span class="muted">on ${esc(p.topics.join(", ") || "this topic")}${r.context.country_name ? " for " + esc(r.context.country_name) : ""}</span></div>
    <p class="muted" style="font-size:13px;margin:0 0 14px">Built from ${p.events} recorded contribution${p.events === 1 ? "" : "s"} on this topic: owning or writing a document counts most, editing and answering questions next, attending a meeting least. Recent work counts more than old work, and work for another country counts a third. Seniority is only a small tie-breaker.</p>
    <h4 style="margin:0 0 8px;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)">Track record</h4>
    <ul class="track">${p.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <div class="modal-actions">${p.email ? `<a class="btn" href="mailto:${esc(p.email)}?subject=${subject}">Ask ${esc(p.name.split(" ")[0])} by email</a>` : ""}</div>`;
  $("#modal").classList.remove("hidden");
}

function mergeExperts(sections) {
  const seen = new Map();
  for (const sec of sections) for (const p of sec.experts || []) if (!seen.has(p.id) || seen.get(p.id).score < p.score) seen.set(p.id, p);
  return [...seen.values()].sort((a, b) => b.score - a.score).slice(0, 4);
}

function renderExperts(r) {
  const el = $("#experts-card");
  const c = r.context;
  const gaps = r.sections.filter((s) => s.status === "missing" || s.status === "partial");
  const shaky = r.sections.filter((s) => s.status === "contested" || s.status === "informal");
  let mode = "info", title = "Who knows this", sub = "reputation on this topic, not seniority", experts = r.experts;
  if (gaps.length) { mode = "contact"; title = "No reliable answer, ask"; sub = "ranked by track record on this topic and country"; experts = mergeExperts(gaps); }
  else if (shaky.length) { mode = "confirm"; title = "Worth confirming with"; sub = "the answer rests on an informal or disputed source"; experts = mergeExperts(shaky); }
  el.className = `card experts mode-${mode}`;
  const local = experts.filter((p) => p.in_country !== false);
  let fallback = false;
  if (local.length) experts = local; else if (experts.length && c.country_name) { fallback = true; sub = `no ${c.country_name} specialist on record for this topic, showing the closest expertise`; }
  if (!experts.length) { el.innerHTML = `<h3 class="card-title">${title}</h3><div class="empty">No expertise signals for these topics.</div>`; return; }
  const subject = encodeURIComponent(`Question: ${r.question}`);
  const body = encodeURIComponent(`Hi,\n\nGrounded could not find a reliable answer to:\n"${r.question}"\n\nYou were suggested as the person most likely to know. Could you help?\n\nThanks`);
  el.innerHTML = `<h3 class="card-title" style="margin-bottom:2px">${title}</h3><p class="muted" style="font-size:12.5px;margin:0 0 12px">${sub}</p>
    ${experts.map((p) => personCard(p, mode !== "info" && p.email ? `<a class="contact" href="mailto:${esc(p.email)}?subject=${subject}&body=${body}" title="Email ${esc(p.name)}">Ask</a>` : "")).join("")}`;
}

function statusTag(e) {
  return e.status === "needs_update" ? `<span class="tag-status">update requested</span>` : "";
}

function evidenceMeta(e) {
  return `<span class="doctype ${esc(e.doc_type)}">${esc(e.doc_type)}</span>${statusTag(e)}
    <span>${esc(e.source_system)}</span>
    <span>${esc(e.country_name)}${e.client ? " · " + esc(e.client) : ""}</span>
    <span>${e.owner ? "Owner: " + esc(e.owner) + (e.owner_active === false ? " (left)" : "") : e.author ? "Author: " + esc(e.author) + " (no owner)" : "No owner"}</span>
    <span>Updated ${fmtDate(e.updated_at)}</span>`;
}

function renderEvidence(r) {
  $("#evcount").textContent = r.evidence.length ? `· ${r.evidence.length}` : "";
  $("#evidence-card").classList.toggle("hidden", !r.evidence.length);
  if (!r.evidence.length) { $("#evidence").innerHTML = `<div class="empty">Nothing was cited, so nothing is claimed.</div>`; return; }
  $("#evidence").innerHTML = r.evidence.map((e) => `
    <div class="evidence-item" data-ev="${e.id}">
      <div class="ev-id ${e.contested ? "contested" : ""}">${e.id}</div>
      <div style="min-width:0">
        <div class="ev-title">${esc(e.title)}</div>
        <div class="ev-meta"><span class="doctype ${esc(e.doc_type)}">${esc(e.doc_type)}</span><span>${e.owner ? esc(e.owner) : e.author ? esc(e.author) + " (no owner)" : "No owner"}</span><span>${fmtDate(e.updated_at)}</span><span>§ ${esc(e.section)}, lines ${e.line_start}–${e.line_end}</span></div>
      </div>
      <div class="conf"><span title="Confidence: how well this passage matches the question and how much it can be trusted">${pct(e.confidence)}%</span><button class="eye" type="button" data-ev="${e.id}" title="Why this confidence">${EYE}</button></div>
    </div>`).join("");
}

function shortMeta(e) {
  return `<span class="doctype ${esc(e.doc_type)}">${esc(e.doc_type)}</span>${statusTag(e)}<span>${e.owner ? esc(e.owner) + (e.owner_active === false ? " (left)" : "") : e.author ? esc(e.author) + " (no owner)" : "no owner"}</span><span>${fmtDate(e.updated_at)}</span>`;
}

const who = (e) => e.owner || e.author || "an unknown author";
const typeName = (e) => ({ chat: "Teams message", email: "email", ticket: "ticket", meeting: "meeting note", wiki: "note", policy: "policy", procedure: "procedure", manual: "manual", checklist: "checklist", analysis: "analysis" }[e.doc_type] || e.doc_type);
const A = (label, action, doc, extra = "", cls = "") => `<button class="act ${cls}" type="button" data-action="${action}" data-doc="${esc(doc)}" ${extra}>${label}</button>`;

function issueCard(id, kind, label, headline, did, actions, items) {
  return `<article class="issue" id="issue-${id}" data-docs="${items.map((i) => i.document_id).join(",")}">
    <div class="issue-head"><span class="badge ${kind}">${label}</span><span class="issue-inspect">${items.map((i) => `<button class="linkbtn slim" data-ev="${i.id}">${i.id} ${esc(i.title.length > 34 ? i.title.slice(0, 33) + "…" : i.title)}</button>`).join("")}</span></div>
    <p class="issue-headline">${headline}</p>
    ${did ? `<p class="issue-did">${did}</p>` : ""}
    <div class="issue-actions">${actions}</div>
    <div class="issue-done hidden"></div>
  </article>`;
}

function renderReview(r) {
  const rv = r.review;
  $("#reviewcount").textContent = r.review_count;
  if (!r.review_count) { $("#tab-review").innerHTML = `<div class="empty">No issues. Nothing conflicting, duplicated, outdated or from the wrong country was found near this question.</div>`; return; }
  let html = `<p class="rintro">Problems found around this question. Each one can be fixed here, and the fix applies to everyone's next answer.</p>`;
  let n = 0;
  for (const c of rv.conflicts) {
    const k = c.kept, j = c.rejected;
    const facts = (d, side) => `<b>${esc(side === "k" ? d.kept : d.rejected)} ${esc(d.unit)}</b>`;
    const headline = `The ${typeName(j)} from ${esc(who(j))} (${fmtDate(j.updated_at)}) says ${c.diffs.map((d) => facts(d, "r")).join(", ")}. The ${typeName(k)} owned by ${esc(who(k))} (${fmtDate(k.updated_at)}) says ${c.diffs.map((d) => facts(d, "k")).join(", ")}.`;
    const did = `The answer uses the ${typeName(k)}. ${esc(c.reason)}`;
    const actions =
      A(`${cap(typeName(k))} is right, retract the ${typeName(j)}`, "retract", j.document_id, "", "primary") +
      A(`${cap(typeName(j))} is right, ask ${esc(who(k))} to update the ${typeName(k)}`, "request_update", k.document_id, `data-note="Conflicting value reported: ${esc(j.title)}"`) +
      A(`Ask ${esc(who(j))} for the source`, "request_update", j.document_id, `data-note="Please add the legal source for this change"`);
    html += issueCard(++n, "warn", "Conflict", headline, did, actions, [k, j]);
  }
  for (const d of rv.duplicates) {
    const headline = `<b>${esc(d.duplicate.title)}</b> (${esc(who(d.duplicate))}, ${fmtDate(d.duplicate.updated_at)}) repeats content from <b>${esc(d.kept.title)}</b>, which ${esc(who(d.kept))} owns. Copies drift out of date.`;
    html += issueCard(++n, "", "Duplicate", headline, `The answer uses the owned original.`, A("Archive the copy", "archive", d.duplicate.document_id, "", "primary") + A(`Ask ${esc(who(d.duplicate))} to remove it`, "request_update", d.duplicate.document_id, `data-note="Duplicate of ${esc(d.kept.title)}"`), [d.kept, d.duplicate]);
  }
  for (const o of rv.outdated) {
    const i = o.item;
    const headline = `<b>${esc(i.title)}</b> is an old version that people can still find. ${esc(i.trust.signals.supersession.note)}.`;
    html += issueCard(++n, "", "Outdated", headline, `The answer uses the newer version.`, A("Archive the old version", "archive", i.document_id, "", "primary") + (i.owner_active === false ? `<span class="act-note">Owner ${esc(who(i))} has left, so nobody will update it.</span>` : A(`Ask ${esc(who(i))} to archive it`, "request_update", i.document_id, `data-note="Superseded version still findable"`)), [i]);
  }
  for (const o of rv.stale || []) {
    const i = o.item;
    const owner = who(i);
    const me = $("#user").value;
    const isOwner = me && (me === i.owner_id || (!i.owner_id && me === i.author_id));
    const period = (i.trust.signals.freshness.note.match(/is (\d+) days/) || [])[1];
    const headline = `<b>${esc(i.title)}</b> was used in the answer but has not been edited or confirmed since ${fmtDate(i.validated_at || i.updated_at)}${period ? `, longer than the ${period}-day review period for a ${esc(typeName(i))}` : ""}.`;
    html += issueCard(++n, "warn", "Review overdue", headline, `Still used, with reduced freshness. Confirming keeps the answer trustworthy without rewriting the document.`,
      (isOwner ? A("I own this and confirm it is still valid", "validate", i.document_id, "", "primary") : A(`Ask ${esc(owner)} to confirm it is still valid`, "request_update", i.document_id, `data-note="Review overdue: please confirm the document is still valid or update it"`, "primary")), [i]);
  }
  for (const o of rv.out_of_scope) {
    const i = o.item;
    const headline = `<b>${esc(i.title)}</b> applies to ${esc(i.country_name)}, this question is about ${esc(r.context.country_name || "another country")}. It was excluded so the wrong rule is not applied.`;
    html += issueCard(++n, "grey", "Wrong country", headline, "", A("Fine, nothing to fix", "dismiss", i.document_id) + A(`Country tag looks wrong, ask ${esc(who(i))}`, "request_update", i.document_id, `data-note="Country tag may be wrong"`), [i]);
  }
  $("#tab-review").innerHTML = html;
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

async function reviewAction(btn) {
  if (btn.dataset.inline) {
    btn.disabled = true;
    const res = await fetch("/api/review/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: btn.dataset.action, document_id: btn.dataset.doc, actor_id: $("#user").value || null }) }).then((x) => x.json());
    btn.textContent = "Confirmed valid today"; toast(`“${res.title}” confirmed still valid`, state.result ? { label: "Ask again", fn: ask } : null);
    return;
  }
  const issue = btn.closest(".issue");
  const action = btn.dataset.action, doc = btn.dataset.doc;
  const done = issue.querySelector(".issue-done");
  const finish = (msg, undoDoc) => {
    issue.classList.add("resolved");
    done.innerHTML = `✓ ${msg}${undoDoc ? ` · <button class="undo" type="button" data-action="restore" data-doc="${esc(undoDoc)}">Undo</button>` : ""}`;
    done.classList.remove("hidden");
  };
  if (action === "dismiss") { finish("Dismissed for this question."); return; }
  if (action === "restore") {
    await fetch("/api/review/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "restore", document_id: doc }) });
    issue.classList.remove("resolved"); done.classList.add("hidden"); toast("Restored"); return;
  }
  btn.disabled = true;
  const res = await fetch("/api/review/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, document_id: doc, question: state.result.question, actor_id: $("#user").value || null, note: btn.dataset.note || null }) }).then((x) => x.json());
  btn.disabled = false;
  if (action === "validate") finish(`“${esc(res.title)}” confirmed still valid today. Freshness restored.`, null);
  else if (action === "retract") finish(`“${esc(res.title)}” retracted. It will not be used in answers again.`, doc);
  else if (action === "archive") finish(`“${esc(res.title)}” archived. It will not be used in answers again.`, doc);
  else if (action === "request_update") finish(`${esc(res.task.assignee)} has been asked to update “${esc(res.title)}”.${res.task.email ? ` <a href="mailto:${esc(res.task.email)}?subject=${encodeURIComponent("Please update: " + res.title)}&body=${encodeURIComponent((btn.dataset.note || "") + "\n\nRaised from the question: " + state.result.question)}">Send the email</a>` : ""}`, doc);
  toast(action === "request_update" ? "Update requested" : action === "validate" ? "Confirmed valid" : "Knowledge base updated", { label: "Ask again", fn: ask });
}

function renderTrace(r) {
  const p = r.pipeline;
  const c = r.context;
  let html = `<div class="subq" style="margin:0 0 14px"><b>Context</b> ${esc(c.country_name || "any country")}${c.country_source ? ` <span class="rw">(${esc(c.country_source)})</span>` : ""} · ${esc(c.client || "no client")} · ${esc(c.team || "any domain")} · ${esc(c.intent)} question · topics: ${c.topics.map((t) => t.replace(/_/g, " ")).join(", ") || "—"}</div>`;
  html += `<ol class="steps">${p.steps.map((s, i) => `<li><span class="n">${i + 1}</span><div><b>${esc(s.name)}</b><span>${esc(s.detail)}</span></div></li>`).join("")}</ol>`;
  html += `<h4 style="margin:18px 0 6px;font-size:14px">Sub-questions and rewrites</h4>`;
  for (const s of r.sections) {
    html += `<div class="subq"><b>${esc(s.id)}</b> ${esc(s.question)}<br><span class="rw">Also searched as: ${s.rewrites.map(esc).join(" · ") || "—"}</span><br><span class="rw">${s.candidates_considered} candidate passages considered</span></div>`;
  }
  const h = state.health || {};
  html += `<p class="muted" style="font-size:12.5px;margin-top:14px">Index: ${h.documents ?? "?"} documents, ${h.chunks ?? "?"} passages, ${h.people ?? "?"} people, ${h.edges ?? "?"} graph edges · Embeddings: ${p.embedding_backend === "ollama" ? "nomic-embed-text (local Ollama container)" : "offline hashed embeddings"} · Answer text is verbatim from the cited passages, so nothing can be hallucinated.</p>`;
  $("#tab-trace").innerHTML = html;
}

const REL_TEXT = { owns: "owns it", authored: "wrote it", edited: "edited it", reviewed: "reviewed it", attended: "attended the meeting", assigned: "is assigned to it", answered: "answered on it", consulted: "was consulted on it" };
function provenance(e) {
  const g = state.result && state.result.graph;
  if (!g) return "";
  const byPerson = new Map();
  for (const l of g.links) {
    if (l.to !== `doc:${e.document_id}` || !l.from.startsWith("person:")) continue;
    const pid = l.from.slice(7);
    const p = g.people.find((x) => x.id === pid);
    if (!p) continue;
    const acts = byPerson.get(pid) || { p, acts: [] };
    acts.acts.push(`${REL_TEXT[l.rel] || l.rel}${l.at ? " (" + fmtDate(l.at) + ")" : ""}`);
    byPerson.set(pid, acts);
  }
  if (!byPerson.size) return "";
  return `<h4 style="margin:0 0 8px;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)">Who stands behind it</h4>
    <ul class="track" style="margin-bottom:18px">${[...byPerson.values()].map(({ p, acts }) => `<li><b>${esc(p.name)}</b>${p.active ? "" : " (left the company)"} · ${esc(p.role)} · ${acts.map(esc).join(", ")}</li>`).join("")}</ul>`;
}

function signalRow(name, sig) {
  const cls = sig.value >= 0.7 ? "" : sig.value >= 0.4 ? "mid" : "low";
  return `<div class="signal"><span class="name">${name}</span><div class="bar"><i class="${cls}" style="width:${pct(sig.value)}%"></i></div><span class="snote">${esc(sig.note)}</span></div>`;
}

function openEvidence(id) {
  const e = state.evidenceById[id];
  if (!e) return;
  const s = e.trust.signals;
  $("#modal-body").innerHTML = `
    <button class="close" data-close>✕</button>
    <h3><span class="ev-id ${e.contested ? "contested" : ""}" style="padding:0 8px">${e.id}</span> ${esc(e.title)}</h3>
    <div class="sub">${evidenceMeta(e)}${e.version ? `<span>v${esc(e.version)}</span>` : ""}</div>
    <div class="quotebox"><div class="loc">${esc(e.location)} · § ${esc(e.section)} · lines ${e.line_start}–${e.line_end}</div>${esc(e.text)}</div>
    <div class="confrow"><b>Confidence ${pct(e.confidence)}%</b><span class="muted">= match to the question ${pct(Math.min(1, e.relevance / 0.8))}% · trust in the source ${pct(e.trust.total)}%</span></div>
    <h4 style="margin:0 0 10px;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)">Why this trust</h4>
    <div class="signals">
      ${signalRow("Freshness", s.freshness)}${signalRow("Owner", s.owner)}${signalRow("Scope", s.scope)}
      ${signalRow("Authority", s.authority)}${signalRow("Channel", s.channel)}${signalRow("Supersession", s.supersession)}
    </div>
    ${provenance(e)}
    <div class="modal-actions">
      <a class="btn secondary" href="${esc(e.url)}" target="_blank" rel="noopener">Open in ${esc(e.source_system)} ↗</a>
      <button class="btn" data-doc="${esc(e.document_id)}" data-from="${e.line_start}" data-to="${e.line_end}">Open document at line ${e.line_start}</button>
    </div>`;
  $("#modal").classList.remove("hidden");
}

async function openDocument(id, from, to) {
  const d = await fetch(`/api/documents/${encodeURIComponent(id)}`).then((r) => r.json());
  from = Number(from); to = Number(to);
  const lines = d.lines.map((t, i) => {
    const n = i + 1;
    const hl = n >= from && n <= to ? "hl" : "";
    const h = t.startsWith("## ") || n === 1 ? "h" : "";
    return `<div class="line ${hl} ${h}" ${n === from ? 'id="target-line"' : ""}><span class="ln">${n}</span><span class="lt">${esc(t.replace(/^## /, ""))}</span></div>`;
  }).join("");
  $("#drawer-body").innerHTML = `
    <button class="close" data-close>✕</button>
    <div class="doc-head">
      <div class="sub" style="margin-bottom:6px"><span class="doctype ${esc(d.doc_type)}">${esc(d.doc_type)}</span><span>${esc(d.source_system)}</span>${d.version ? `<span>v${esc(d.version)}</span>` : ""}</div>
      <h2>${esc(d.title)}</h2>
      <dl class="kv" style="margin-top:10px">
        <dt>Owner</dt><dd>${d.owner_name ? esc(d.owner_name) + `<small>${esc(d.owner_role)}</small>` : "No owner on record"}</dd>
        <dt>Author</dt><dd>${esc(d.author_name || "—")}</dd>
        <dt>Scope</dt><dd>${esc(d.country_name)}${d.client ? " · " + esc(d.client) : ""}${d.team ? " · " + esc(d.team) : ""}</dd>
        <dt>Updated</dt><dd>${fmtDate(d.updated_at)}<small>created ${fmtDate(d.created_at)}</small></dd>
        <dt>Location</dt><dd style="font-weight:500">${esc(d.location)}<small><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.url)}</a></small></dd>
      </dl>
      ${d.status && d.status !== "active" ? `<div class="warn-box">${{ archived: "Archived: no longer used in answers.", retracted: "Retracted: marked as incorrect, no longer used in answers.", needs_update: "Update requested from the owner." }[d.status] || d.status}</div>` : ""}
      ${d.superseded_by ? `<div class="warn-box">⚠ This version is superseded by <b>${esc(d.superseded_by.title)}</b> (${fmtDate(d.superseded_by.updated_at)}). Do not apply it.</div>` : ""}
    </div>
    ${d.open_tasks && d.open_tasks.length ? `<div class="warn-box">${d.open_tasks.map((t) => `${({ request_update: "Update requested", confirm_valid: "Review overdue", reassign_owner: "Needs a new owner" })[t.kind] || t.kind}${t.assignee ? " · " + esc(t.assignee) : ""}: ${esc(t.note || "")}`).join("<br>")}</div>` : ""}
    <div class="doc-tools">
      <span class="muted">${d.review_due ? `Review overdue (period ${d.review_period_days} days)` : `Next review due ${d.review_period_days} days after the last edit or confirmation`}${d.validated_at ? ` · confirmed valid ${fmtDate(d.validated_at)}` : ""}</span>
      <button class="act ${d.review_due ? "primary" : ""}" type="button" data-action="validate" data-doc="${esc(d.id)}" data-inline="1">Confirm still valid</button>
    </div>
    <div class="doc-lines">${lines}</div>
    ${d.versions && d.versions.length ? `<h4 class="hist-title">History</h4><ul class="track hist">${d.versions.map((v) => `<li><b>v${v.version_no}</b> · ${fmtDate(v.changed_at)}${v.changed_by ? " · " + esc(v.changed_by) : ""} · ${esc(v.change_summary || "")}</li>`).join("")}</ul>` : `<p class="muted" style="font-size:12.5px;margin-top:12px">Seeded document. Changes picked up by a sync will appear here as versions with a summary of what changed.</p>`}`;
  $("#drawer").classList.remove("hidden");
  requestAnimationFrame(() => { const t = $("#target-line"); if (t) t.scrollIntoView({ block: "center" }); });
}

/* Add knowledge: a user or a meeting agent adds a note or decision; it is embedded and citable at once. */
function openAddKnowledge(pane = "write") {
  const m = state.meta;
  const me = $("#user").value;
  $("#modal-body").innerHTML = `
    <button class="close" data-close>✕</button>
    <h3>Add knowledge</h3>
    <div class="tabs small" style="margin:10px 0 16px">
      <button class="tab ${pane === "write" ? "active" : ""}" data-pane="write" type="button">Write a note</button>
      <button class="tab ${pane === "sources" ? "active" : ""}" data-pane="sources" type="button">Connected sources</button>
    </div>
    <div id="pane-write" class="${pane === "write" ? "" : "hidden"}">
      <p class="muted" style="font-size:13px;margin:0 0 12px">Notes, decisions and answers you would otherwise leave in a chat. Indexed immediately, owned by you, citable in the next question.</p>
      <form id="addform" class="form">
        <label>Title<input name="title" required placeholder="e.g. Decision: Colruyt meal voucher provider from 2027"></label>
        <label>Content<textarea name="text" required placeholder="Write it as you would tell a colleague. One fact per sentence works best."></textarea></label>
        <div class="row">
          <label>Type<select name="doc_type"><option value="wiki">Note</option><option value="meeting">Meeting decision</option><option value="analysis">Analysis</option><option value="email">Email</option><option value="chat">Chat message</option></select></label>
          <label>Owner<select name="owner_id">${state.people.filter((p) => p.active).map((p) => `<option value="${p.id}" ${p.id === me ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
        </div>
        <div class="row">
          <label>Country<select name="country"><option value="">Global</option>${m.countries.map((c) => `<option value="${c.id}">${esc(c.label)}</option>`).join("")}</select></label>
          <label>Client<select name="client"><option value="">None</option>${m.clients.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}</select></label>
        </div>
        <label>Topics<div class="topics-pick">${m.topics.map((t) => `<label><input type="checkbox" name="topics" value="${t.id}">${esc(t.label)}</label>`).join("")}</div></label>
        <div class="modal-actions"><button type="button" class="btn secondary" data-close>Cancel</button><button type="submit" class="btn">Add to knowledge base</button></div>
      </form>
    </div>
    <div id="pane-sources" class="${pane === "sources" ? "" : "hidden"}">
      <p class="muted" style="font-size:13px;margin:0 0 12px">Each source has a connector that pulls content through its API and indexes it with owner, date and scope. Without credentials a connector runs on demo data in the same payload shape.</p>
      <div id="connectors"><div class="skeleton"></div><div class="skeleton"></div></div>
      <details class="apihelp"><summary>Push knowledge programmatically</summary>
        <p>Any system can post documents or meeting transcripts directly:</p>
        <pre>POST /api/ingest/documents      {"source": "MyApp", "units": [{"external_id", "title", "doc_type", "sections": [[heading, [sentences]]], "updated_at", "owner_email", "country", "client"}]}
POST /api/ingest/meeting        {"id", "subject", "transcript", "createdDateTime", "organizer", "attendees", "client", "country"}
POST /api/connectors/{name}/sync?since=YYYY-MM-DD</pre>
        <p>Live mode needs the environment variables listed per connector (Microsoft Graph app registration for SharePoint, Teams, Outlook and Meetings; an Atlassian API token for Jira and Confluence).</p>
      </details>
    </div>`;
  $("#modal").classList.remove("hidden");
  $("#modal-body").querySelectorAll("[data-pane]").forEach((b) => b.addEventListener("click", () => {
    $("#modal-body").querySelectorAll("[data-pane]").forEach((x) => x.classList.toggle("active", x === b));
    $("#pane-write").classList.toggle("hidden", b.dataset.pane !== "write");
    $("#pane-sources").classList.toggle("hidden", b.dataset.pane !== "sources");
  }));
  loadConnectors();
  $("#addform").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = { title: fd.get("title"), text: fd.get("text"), doc_type: fd.get("doc_type"), owner_id: fd.get("owner_id") || null, country: fd.get("country") || null, client: fd.get("client") || null, topics: fd.getAll("topics") };
    const r = await fetch("/api/knowledge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((x) => x.json());
    closeOverlays();
    fetch("/api/health").then((x) => x.json()).then(updateHealth);
    toast(`Indexed as ${r.id} · “${r.title}”`, state.result ? { label: "Ask again", fn: ask } : null);
  });
}

async function loadConnectors() {
  const [list, fr] = await Promise.all([fetch("/api/connectors").then((r) => r.json()), fetch("/api/freshness").then((r) => r.json())]);
  const el = $("#connectors");
  if (!el) return;
  const tasks = Object.entries(fr.open_tasks || {}).map(([k, v]) => `${v} ${({ request_update: "update requests", confirm_valid: "reviews pending", reassign_owner: "orphaned" })[k] || k}`).join(", ");
  const fresh = `<div class="freshline"><b>Freshness</b> ${fr.fresh_180d}/${fr.documents} documents touched in the last 180 days · ${fr.review_overdue} review${fr.review_overdue === 1 ? "" : "s"} overdue · ${fr.versions_recorded} versions recorded${tasks ? " · " + tasks : ""}<br><span class="muted">Every connector delta-syncs every ${fr.auto_sync_minutes} min and on webhook; unchanged documents are skipped by content hash, changed ones get a new version and only changed sections are re-embedded. Overdue documents raise a "confirm still valid" task for their owner.</span> <button class="linkbtn slim" type="button" id="sweepbtn">Run freshness sweep</button></div>`;
  const ago = (iso) => { const m = Math.round((Date.now() - new Date(iso)) / 60000); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`; };
  el.innerHTML = fresh + list.map((c) => `
    <div class="connector" data-connector="${esc(c.name)}">
      <div class="connector-main">
        <div class="connector-top"><b>${esc(c.label)}</b><span class="badge ${c.mode === "live" ? "ok" : "grey"}" title="${c.mode === "live" ? "Credentials found" : "No credentials set: " + c.required_env.join(", ")}">${c.mode === "live" ? "Live" : "Demo data"}</span><span class="muted">${c.documents} document${c.documents === 1 ? "" : "s"}</span></div>
        <div class="connector-desc">${esc(c.description)}</div>
        <div class="connector-last muted">${c.last_sync ? `Last sync ${ago(c.last_sync.finished_at)} (${c.last_sync.trigger}): ${c.last_sync.fetched} fetched, ${c.last_sync.inserted} new, ${c.last_sync.updated} changed, ${c.last_sync.unchanged} unchanged${c.last_sync.archived ? ", " + c.last_sync.archived + " archived" : ""}` : "Never synced"}</div>
      </div>
      <button class="act primary" type="button" data-sync="${esc(c.name)}">Sync now</button>
    </div>`).join("");
  const sw = $("#sweepbtn");
  if (sw) sw.addEventListener("click", async () => { const r = await fetch("/api/freshness/sweep", { method: "POST" }).then((x) => x.json()); toast(`Sweep: ${r.confirm_valid} review request${r.confirm_valid === 1 ? "" : "s"}, ${r.reassign_owner} orphaned document${r.reassign_owner === 1 ? "" : "s"} flagged`); loadConnectors(); });
  el.querySelectorAll("[data-sync]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Syncing…";
    const r = await fetch(`/api/connectors/${b.dataset.sync}/sync`, { method: "POST" }).then((x) => x.json());
    b.disabled = false; b.textContent = "Sync now";
    toast(`${r.label || r.connector}: ${r.fetched} fetched, ${r.inserted} new, ${r.updated} changed, ${r.unchanged} unchanged`, state.result ? { label: "Ask again", fn: ask } : null);
    fetch("/api/health").then((x) => x.json()).then(updateHealth);
    loadConnectors();
  }));
}

function toast(msg, action) {
  const t = $("#toast");
  t.innerHTML = `<span>${esc(msg)}</span>${action ? `<button type="button">${esc(action.label)}</button>` : ""}`;
  if (action) t.querySelector("button").addEventListener("click", () => { t.classList.add("hidden"); action.fn(); });
  t.classList.remove("hidden");
  clearTimeout(t._timer); t._timer = setTimeout(() => t.classList.add("hidden"), 6000);
}

function copyAnswer() {
  const r = state.result;
  if (!r) return;
  const lines = [`Q: ${r.question}`, `${r.verdict} · confidence ${pct(r.confidence)}%`, ""];
  for (const s of r.sections) {
    if (r.sections.length > 1) lines.push(`${s.id}. ${s.question}`);
    for (const seg of s.segments) lines.push(`${seg.text} [${seg.evidence.join(", ")}]`);
    if (s.note) lines.push(`Note: ${s.note}`);
    lines.push("");
  }
  lines.push("Sources:");
  for (const e of r.evidence) lines.push(`${e.id} ${e.title} · ${e.doc_type} · owner ${e.owner || "none"} · updated ${e.updated_at} · confidence ${pct(e.confidence)}% · § ${e.section} lines ${e.line_start}-${e.line_end} · ${e.url}`);
  navigator.clipboard.writeText(lines.join("\n")).then(() => toast("Answer copied with sources"));
}

function closeOverlays() {
  if (!$("#drawer").classList.contains("hidden")) { $("#drawer").classList.add("hidden"); return; }
  $("#modal").classList.add("hidden");
}

init();
