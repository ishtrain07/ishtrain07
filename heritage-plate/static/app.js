// Heritage Plate front end: plain JS, no build step.
const $ = (id) => document.getElementById(id);
const state = { recipes: [], trace: [] };

const FOCUS = {
  diabetes: { key: "net_carbs_g", label: "Net carbs", unit: "g",
    hint: "For diabetes we watch net carbs: the carbs that turn into blood sugar (total carbs minus fibre). Lower per serving is better." },
  bp: { key: "sodium_mg", label: "Sodium", unit: "mg",
    hint: "For blood pressure we watch sodium, which mostly comes from salt. Lower per serving is better." },
  cholesterol: { key: "fat_g", label: "Fat", unit: "g",
    hint: "For cholesterol we watch fat, mostly from ghee, butter and oil. Lower per serving is better." },
};

function updateFocusHint() {
  $("focusHint").textContent = `${FOCUS[$("condition").value].hint} Tap "Adapt" on a dish to see its lighter version.`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  if (data.trace) addTrace(data.trace);
  return data;
}

function addTrace(entries) {
  state.trace.push(...entries);
  $("trace").innerHTML = state.trace
    .map((t) => `<li><span class="tier">${esc(t.tier)}</span>${esc(t.step)}: <code>${esc(t.model)}</code>${t.ms ? `, ${t.ms} ms` : ""}${t.tokens ? `, ${t.tokens} tokens` : ""}${t.fallback ? " (fallback)" : ""}</li>`)
    .join("");
}

async function busy(btn, fn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.classList.add("spin");
  try { return await fn(); } finally { btn.disabled = false; btn.classList.remove("spin"); btn.textContent = label; refreshButtons(); }
}

function refreshButtons() {
  $("adaptAll").disabled = !state.recipes.some((r) => !r.changes);
  $("plan").disabled = state.recipes.length === 0;
}

function bars(recipe) {
  const f = FOCUS[recipe.condition || $("condition").value];
  const before = recipe.original.nutrition[f.key];
  const after = recipe.nutrition[f.key];
  const max = Math.max(before, after, 1);
  const pct = before > 0 ? Math.round(((before - after) / before) * 100) : 0;
  return `
    <div class="compare">
      <div class="bar-label"><span>Before: ${f.label}</span><span>${before} ${f.unit}</span></div>
      <div class="bar"><span style="width:${(before / max) * 100}%"></span></div>
      <div class="bar-label"><span>After: ${f.label}</span><span>${after} ${f.unit}</span></div>
      <div class="bar after"><span style="width:${(after / max) * 100}%"></span></div>
      ${pct > 0 ? `<div class="win">${pct}% less ${f.label.toLowerCase()} per serving, same dish</div>` : ""}
    </div>`;
}

function recipeCard(r, i) {
  const n = r.nutrition;
  const adapted = Boolean(r.changes);
  const uncounted = n.uncounted?.length ? `<p class="warn">Not counted (not in our food table yet): ${esc(n.uncounted.join(", "))}</p>` : "";
  return `
    <article class="card recipe">
      <span class="tag">${esc(r.meal)}${adapted ? " · adapted" : ""}</span>
      <h3>${esc(r.name)}</h3>
      ${r.source_text ? `<p class="quote">“${esc(r.source_text)}”</p>` : ""}
      <div class="chips">
        <span class="chip">${n.net_carbs_g} g net carbs</span>
        <span class="chip">${Math.round(n.kcal)} kcal</span>
        <span class="chip">${n.protein_g} g protein</span>
        <span class="chip">serves ${r.servings}</span>
      </div>
      ${adapted ? bars(r) : ""}
      ${adapted ? `<ul class="changes">${r.changes.map((c) => `<li>${esc(c.what)}<small>${esc(c.why)}</small></li>`).join("")}</ul>` : ""}
      ${adapted && r.cooking_tip ? `<p class="quote">Tip: ${esc(r.cooking_tip)}</p>` : ""}
      ${uncounted}
      <details class="ing"><summary>Ingredients (${r.ingredients.length})</summary>
        <ul>${r.ingredients.map((g) => `<li>${esc(g.item)}: ${g.grams} g</li>`).join("")}</ul>
      </details>
      <div class="actions">
        ${adapted ? "" : `<button class="ghost" data-adapt="${i}">Adapt for Mum/Dad</button>`}
      </div>
    </article>`;
}

function renderCookbook() {
  $("cookbook").innerHTML = state.recipes.length
    ? state.recipes.map(recipeCard).join("")
    : `<p class="empty">No recipes yet. Add one above or load the demo family.</p>`;
  refreshButtons();
}

async function adaptOne(i) {
  const { recipe } = await api("/api/adapt", { recipe: state.recipes[i], condition: $("condition").value });
  state.recipes[i] = recipe;
  renderCookbook();
}

function renderPlan(plan) {
  const slot = (v) => (v ? esc(v) : "—");
  $("planOut").innerHTML = `
    <div class="card">
      <p class="tag">Message for your parent (${esc(plan.language)})</p>
      <p class="parent-msg">${esc(plan.message_for_parent)}</p>
    </div>
    <div class="card table-scroll">
      <table class="week">
        <thead><tr><th>Day</th><th>Breakfast</th><th>Lunch</th><th>Dinner</th><th>Treat</th></tr></thead>
        <tbody>${plan.days.map((d) => `<tr><td><b>${esc(d.day)}</b></td><td>${slot(d.breakfast)}</td><td>${slot(d.lunch)}</td><td>${slot(d.dinner)}</td><td>${slot(d.dessert)}</td></tr>`).join("")}</tbody>
      </table>
    </div>
    <div class="cols">
      <div class="card"><h3>Shopping list (whole week)</h3>
        <ul class="shop">${plan.shopping_list.map((s) => `<li>${esc(s.item)}: ${s.grams >= 1000 ? (s.grams / 1000).toFixed(1) + " kg" : s.grams + " g"}</li>`).join("")}</ul>
      </div>
      <div class="card"><h3>Tips</h3><ul>${plan.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>
    </div>`;
}

// ---------- events ----------
$("loadDemo").addEventListener("click", (e) => busy(e.target, async () => {
  const fam = await api("/api/demo");
  state.recipes = fam.recipes;
  $("condition").value = fam.condition;
  $("language").value = fam.language;
  updateFocusHint();
  $("parseMsg").textContent = `Loaded ${fam.family}: ${fam.parent}.`;
  renderCookbook();
}));

$("parse").addEventListener("click", (e) => busy(e.target, async () => {
  const text = $("recipeText").value.trim();
  const msg = $("parseMsg");
  msg.className = "msg";
  if (text.length < 3) { msg.textContent = "Type or speak a recipe first."; return; }
  try {
    const { recipe } = await api("/api/parse", { text, servings: Number($("servings").value) || null });
    state.recipes.unshift(recipe);
    $("recipeText").value = "";
    msg.textContent = `Added “${recipe.name}” with ${recipe.ingredients.length} ingredients.`;
    renderCookbook();
  } catch (err) { msg.className = "msg error"; msg.textContent = err.message; }
}));

$("cookbook").addEventListener("click", (e) => {
  const i = e.target.dataset.adapt;
  if (i !== undefined) busy(e.target, () => adaptOne(Number(i)).catch((err) => alert(err.message)));
});

$("adaptAll").addEventListener("click", (e) => busy(e.target, async () => {
  const pending = state.recipes.map((r, i) => (r.changes ? null : i)).filter((i) => i !== null);
  await Promise.all(pending.map((i) => adaptOne(i).catch(() => null)));
}));

$("condition").addEventListener("change", () => {
  // A different health focus needs fresh adaptations.
  state.recipes = state.recipes.map((r) => (r.original ? { ...r, ingredients: r.original.ingredients, nutrition: r.original.nutrition, changes: undefined, original: undefined } : r));
  updateFocusHint();
  renderCookbook();
});

$("plan").addEventListener("click", (e) => busy(e.target, async () => {
  try {
    const { plan } = await api("/api/plan", { recipes: state.recipes, condition: $("condition").value, language: $("language").value });
    renderPlan(plan);
  } catch (err) { $("planOut").innerHTML = `<p class="msg error">${esc(err.message)}</p>`; }
}));

// Voice input via the browser's built-in speech recognition, where available.
(() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("mic");
  if (!SR) { mic.disabled = true; mic.title = "Voice input isn't supported in this browser"; return; }
  const rec = new SR();
  rec.lang = "en-IN";
  rec.interimResults = false;
  rec.onresult = (ev) => { $("recipeText").value += (($("recipeText").value ? " " : "") + ev.results[0][0].transcript); };
  rec.onend = () => { mic.textContent = "🎙 Speak"; };
  mic.addEventListener("click", () => { mic.textContent = "Listening…"; rec.start(); });
})();

api("/api/health").then((h) => {
  const b = $("mode");
  b.textContent = h.mode === "live" ? "Live: Nemotron on Nebius" : "Demo mode (no API key)";
  b.classList.toggle("live", h.mode === "live");
}).catch(() => { $("mode").textContent = "Server offline"; });
updateFocusHint();
refreshButtons();
