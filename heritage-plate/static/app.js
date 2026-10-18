// Heritage Plate front end: plain JS, no build step, no external dependencies.
"use strict";

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// ---------- constants ----------
const CONDITIONS = {
  diabetes: {
    label: "Type 2 diabetes", key: "net_carbs_g", nutrient: "net carbs", unit: "g",
    plain: "Net carbs are the carbs that turn into blood sugar (total carbs minus fibre).",
  },
  bp: {
    label: "High blood pressure", key: "sodium_mg", nutrient: "sodium", unit: "mg",
    plain: "Sodium mostly comes from salt and salty sauces. Less sodium helps blood pressure.",
  },
  cholesterol: {
    label: "High cholesterol", key: "sat_fat_g", nutrient: "saturated fat", unit: "g",
    plain: "Saturated fat comes from ghee, butter, cream and fatty meat. Less of it helps cholesterol.",
  },
};

const NUTRIENTS = [
  ["kcal", "Energy", "kcal"],
  ["net_carbs_g", "Net carbs", "g"],
  ["fiber_g", "Fibre", "g"],
  ["protein_g", "Protein", "g"],
  ["fat_g", "Fat", "g"],
  ["sat_fat_g", "Saturated fat", "g"],
  ["sodium_mg", "Sodium", "mg"],
];

const DEFAULT_CUISINES = {
  south_asian: "South Asian (Indian, Pakistani, Bangladeshi, Sri Lankan)",
  east_asian: "East Asian (Chinese, Korean, Japanese)",
  southeast_asian: "Southeast Asian (Filipino, Vietnamese, Thai, Malaysian)",
  continental: "Continental European (Italian, French, British, Eastern European)",
  middle_eastern: "Middle Eastern and North African",
  latin_american: "Latin American and Caribbean",
  other: "home cooking from any tradition",
};
const DEFAULT_LANGUAGES = ["English", "Hindi", "Punjabi", "Gujarati", "Urdu", "Bengali", "Tamil", "Telugu", "Mandarin",
  "Cantonese", "Korean", "Japanese", "Tagalog", "Vietnamese", "Thai", "Arabic", "Farsi", "Spanish", "Portuguese",
  "Italian", "French", "Polish"];

const PLACEHOLDERS = {
  south_asian: "e.g. Masoor dal: 1 katori masoor, half onion, 1 tamatar, a little ghee, jeera, salt",
  east_asian: "e.g. Dad's fried rice: 2 bowls cooked rice, 2 eggs, a handful of peas, 2 spoons soy sauce, a little oil",
  southeast_asian: "e.g. Chicken adobo: 1 kg chicken, half cup soy sauce, half cup vinegar, garlic, bay leaf, a little oil",
  continental: "e.g. Nonna's minestrone: 2 carrots, 1 onion, celery, 1 tin beans, a handful of pasta, olive oil, salt",
  middle_eastern: "e.g. Mujadara: 1 cup lentils, 1 cup rice, 3 onions fried in olive oil, cumin, salt",
  latin_american: "e.g. Arroz con pollo: 2 cups rice, 500 g chicken, 1 onion, 1 pepper, a little oil, salt",
  other: "e.g. Sunday stew: 500 g beef, 3 potatoes, 2 carrots, 1 onion, a spoon of butter, salt",
};

const SPEECH_LANG = {
  English: "en-IN", Hindi: "hi-IN", Punjabi: "pa-IN", Gujarati: "gu-IN", Tamil: "ta-IN", Bengali: "bn-IN",
  Urdu: "ur-PK", Telugu: "te-IN", Mandarin: "zh-CN", Cantonese: "zh-HK", Korean: "ko-KR", Japanese: "ja-JP",
  Tagalog: "fil-PH", Vietnamese: "vi-VN", Thai: "th-TH", Arabic: "ar-SA", Farsi: "fa-IR", Spanish: "es-ES",
  Portuguese: "pt-BR", Italian: "it-IT", French: "fr-FR", Polish: "pl-PL",
};

const FAMILY_COLORS = ["#a63f14", "#2a6640", "#1f4277", "#7a4f00"];
const DAY_NAMES = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };
const SHOP_GROUPS = {
  grain: "Grains and flour", legume: "Beans and lentils", vegetable: "Vegetables", fruit: "Fruit", dairy: "Dairy",
  protein: "Meat, fish and eggs", fat: "Oils and fats", nuts: "Nuts", sauce: "Sauces", sweetener: "Sugar and sweeteners",
  spice: "Spices", other: "Other",
};
const TIERS = {
  nano: { name: "Nemotron Nano", job: "Reads your recipe and turns home measures into ingredients and grams." },
  super: { name: "Nemotron Super", job: "Suggests swaps that keep the dish recognisable but lighter." },
  ultra: { name: "Nemotron Ultra", job: "Plans the week and writes the note for your parent." },
};
const ADAPT_CONCURRENCY = 3;
const LOWER_IS_BETTER = new Set(["kcal", "net_carbs_g", "fat_g", "sat_fat_g", "sodium_mg"]);

// USDA names come in capitals ("BUTTER OIL,ANHYDROUS"); make them easier to read.
function readableRecord(s) {
  const t = String(s ?? "");
  if (t !== t.toUpperCase()) return t;
  const low = t.toLowerCase().replace(/,(?=\S)/g, ", ");
  return low.charAt(0).toUpperCase() + low.slice(1);
}

// ---------- state ----------
const state = {
  condition: "diabetes",
  cuisine: "south_asian",
  language: "English",
  parentName: "",
  family: null,          // {id, family, parent, ...} when a demo family is loaded
  families: [],
  recipes: [],           // [{id, base, adapted, status: idle|busy|error, error}]
  trace: [],
  health: null,
  plan: null,
  planStale: false,
  adaptRun: 0,           // bumps to cancel a running "make every dish lighter"
};

// ---------- helpers ----------
function uid() {
  if (window.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return "r-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

function num(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }

function fmt(v, unit) {
  const n = num(v);
  if (unit === "mg" || unit === "kcal") return String(Math.round(n));
  return n >= 10 ? String(Math.round(n)) : String(Math.round(n * 10) / 10);
}

function grams(g) {
  const n = num(g);
  if (n >= 1000) return (Math.round(n / 100) / 10) + " kg";
  return fmt(n, "g") + " g";
}

function parentWord() {
  const n = state.parentName.trim();
  return n || "Mum or Dad";
}

function shortCuisine(key) {
  const label = (state.health?.cuisines || DEFAULT_CUISINES)[key] || key;
  if (key === "other") return "Home cooking";
  return label.split(" (")[0];
}

function announce(text) {
  const a = $("announce");
  a.textContent = "";
  setTimeout(() => { a.textContent = text; }, 30);
}

let toastTimer;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
}

function readableError(detail, status) {
  if (status === 429) return "Lots of requests right now. Please wait a few minutes and try again.";
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (!d || typeof d !== "object") return String(d);
      const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body" && typeof x === "string").pop() : "";
      const msg = String(d.msg || "is not valid").replace(/^Value error,\s*/i, "");
      return field ? `${field.replace(/_/g, " ")}: ${msg}` : msg;
    });
    return "Please check: " + parts.join("; ") + ".";
  }
  if (detail && typeof detail === "object") return detail.msg ? String(detail.msg) : "Something in the request wasn't right.";
  if (typeof detail === "string" && detail) {
    if (status === 502) return `The AI model didn't answer properly (${detail}). Please try again.`;
    return detail;
  }
  if (status === 502) return "The AI model didn't answer properly. Please try again.";
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return `Request failed (${status}).`;
}

async function api(path, body, timeoutMs = 120000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (err) {
    throw new Error(err.name === "AbortError" ? "This is taking too long. Please try again." : "Can't reach the server. Check your connection and try again.");
  } finally { clearTimeout(timer); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(readableError(data.detail, res.status));
  if (Array.isArray(data.trace)) addTrace(data.trace);
  return data;
}

function baseFields(r) {
  return {
    id: r.id,
    name: r.name,
    servings: r.servings,
    meal: r.meal ?? null,
    ingredients: (r.ingredients || []).map((g) => ({ item: g.item, grams: num(g.grams) })),
    source_text: r.source_text || "",
  };
}

function current(entry) { return entry.adapted || entry.base; }
function findEntry(id) { return state.recipes.find((e) => e.id === id); }

// Elapsed-seconds feedback so waits never feel frozen.
function ticker(el, textFn) {
  const start = Date.now();
  const draw = () => {
    const s = Math.floor((Date.now() - start) / 1000);
    el.innerHTML = textFn(s);
  };
  draw();
  const t = setInterval(draw, 1000);
  return () => clearInterval(t);
}

async function busy(btn, label, fn) {
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  btn.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${esc(label)}</span>`;
  try { return await fn(); } finally {
    btn.removeAttribute("aria-busy");
    btn.innerHTML = old;
    btn.disabled = false;
    refreshButtons();
  }
}

// ---------- trace / under the hood ----------
function addTrace(entries) {
  state.trace.push(...entries.filter((t) => t && typeof t === "object"));
  renderTrace();
}

function renderTiers() {
  const models = state.health?.models || {};
  const counts = { nano: 0, super: 0, ultra: 0 };
  state.trace.forEach((t) => { if (t.tier in counts) counts[t.tier] += 1; });
  $("tiers").innerHTML = Object.entries(TIERS).map(([k, t]) => `
    <div class="tier">
      <div class="tier-name"><span class="tchip ${k}">${esc(k)}</span>${esc(t.name)}</div>
      <div class="tier-job">${esc(t.job)}</div>
      ${models[k] ? `<code>${esc(models[k])}</code>` : ""}
      <div class="tier-count">${counts[k]} call${counts[k] === 1 ? "" : "s"} this session</div>
    </div>`).join("");
}

function renderTrace() {
  renderTiers();
  if (!state.trace.length) return;
  $("trace").innerHTML = state.trace.slice().reverse().map((t) => {
    const tier = ["nano", "super", "ultra"].includes(t.tier) ? t.tier : "nano";
    const bits = [];
    if (t.ms) bits.push(`${(num(t.ms) / 1000).toFixed(1)} s`);
    if (t.tokens) bits.push(`${num(t.tokens)} tokens`);
    const flags = [];
    if (t.cached) flags.push("from cache");
    if (t.fallback) flags.push("used backup rules");
    return `<li><span class="tchip ${tier}">${esc(t.tier)}</span><b>${esc(t.step)}</b>: <code>${esc(t.model)}</code>${bits.length ? ` · ${esc(bits.join(", "))}` : ""}${flags.length ? ` <span class="tflag">(${esc(flags.join(", "))})</span>` : ""}</li>`;
  }).join("");
}

// ---------- settings ----------
function fillSelects() {
  const cuisines = state.health?.cuisines || DEFAULT_CUISINES;
  const langs = state.health?.languages || DEFAULT_LANGUAGES;
  $("cuisine").innerHTML = Object.entries(cuisines).map(([k, v]) => {
    const label = k === "other" ? "Something else / mixed" : v;
    return `<option value="${esc(k)}">${esc(label)}</option>`;
  }).join("");
  $("language").innerHTML = langs.map((l) => `<option value="${esc(l)}">${esc(l)}</option>`).join("");
  if (!(state.cuisine in cuisines)) state.cuisine = Object.keys(cuisines)[0];
  if (!langs.includes(state.language)) state.language = langs[0];
  syncControls();
}

function syncControls() {
  document.querySelectorAll('input[name="condition"]').forEach((r) => { r.checked = r.value === state.condition; });
  $("cuisine").value = state.cuisine;
  $("language").value = state.language;
  $("parentName").value = state.parentName;
  $("recipeText").placeholder = PLACEHOLDERS[state.cuisine] || PLACEHOLDERS.other;
  updateFocusHint();
  updateMicHint();
}

function updateFocusHint() {
  const c = CONDITIONS[state.condition];
  $("focusHint").innerHTML = `Cooking for <b>${esc(c.label.toLowerCase())}</b>. ${esc(c.plain)} Lower per serving is better.`;
}

function setCondition(value) {
  if (!(value in CONDITIONS) || value === state.condition) return;
  state.condition = value;
  state.adaptRun += 1; // stop any running batch; late replies for the old condition are dropped
  let reset = 0;
  state.recipes.forEach((e) => {
    if (e.adapted || e.status !== "idle") reset += 1;
    e.adapted = null; e.status = "idle"; e.error = "";
  });
  $("adaptProgress").hidden = true;
  if (state.plan) state.planStale = true;
  syncControls();
  renderCookbook();
  renderPlan();
  announce(`Now cooking for ${CONDITIONS[value].label}.${reset ? " Dishes are back to their originals; make them lighter again for this focus." : ""}`);
}

// ---------- families ----------
function renderFamilies() {
  const box = $("families");
  if (!state.families.length) {
    box.innerHTML = `<p class="msg error">Demo families couldn't load. You can still add your own recipes below.</p>`;
    return;
  }
  box.innerHTML = state.families.map((f, i) => {
    const initial = (f.family || "?").replace(/^The\s+/i, "").charAt(0).toUpperCase();
    const who = String(f.parent || "").split("(")[0].trim();
    return `
      <button type="button" class="family" data-family="${esc(f.id)}" aria-pressed="${state.family?.id === f.id}">
        <span class="family-top">
          <span class="avatar" style="background:${FAMILY_COLORS[i % FAMILY_COLORS.length]}" aria-hidden="true">${esc(initial)}</span>
          <span>
            <span class="family-name">${esc(f.family)}</span><br>
            <span class="family-parent">Cooking for ${esc(who)}</span>
          </span>
        </span>
        <span class="family-meta">
          <span class="pill">${esc(shortCuisine(f.cuisine))}</span>
          <span class="pill cond-${esc(f.condition)}">${esc(CONDITIONS[f.condition]?.label || f.condition)}</span>
          <span class="pill">${esc(f.language)}</span>
        </span>
        <span class="family-cta">${state.family?.id === f.id ? "Loaded" : "Cook with this family"} <span aria-hidden="true">→</span></span>
      </button>`;
  }).join("");
}

async function loadFamily(id, btn) {
  const cta = btn.querySelector(".family-cta");
  if (cta) cta.textContent = "Loading…";
  try {
    const fam = await api(`/api/demo/${encodeURIComponent(id)}`);
    state.adaptRun += 1;
    state.family = fam;
    state.condition = fam.condition in CONDITIONS ? fam.condition : "diabetes";
    state.cuisine = fam.cuisine;
    state.language = fam.language;
    state.parentName = String(fam.parent || "").split(",")[0].trim().slice(0, 20);
    state.recipes = (fam.recipes || []).map((r) => ({ id: String(r.id || uid()), base: r, adapted: null, status: "idle", error: "" }));
    state.plan = null; state.planStale = false;
    $("adaptProgress").hidden = true;
    $("parseMsg").textContent = "";
    syncControls();
    renderFamilies();
    renderCookbook();
    renderPlan();
    $("s3").scrollIntoView({ block: "start" });
    $("s3").focus({ preventScroll: true });
    announce(`Loaded ${fam.family}: ${state.recipes.length} dishes, cooking for ${fam.parent}.`);
  } catch (err) {
    renderFamilies();
    toast(err.message);
  }
}

// ---------- cookbook ----------
function refreshButtons() {
  const anyBusy = state.recipes.some((e) => e.status === "busy");
  const todo = state.recipes.some((e) => !e.adapted && e.status !== "busy");
  const all = $("adaptAll");
  if (!all.hasAttribute("aria-busy")) {
    all.disabled = !todo;
    all.textContent = state.recipes.length && !todo && !anyBusy ? "Every dish is lighter" : "Make every dish lighter";
  }
  const plan = $("plan");
  if (!plan.hasAttribute("aria-busy")) plan.disabled = state.recipes.length === 0;
  $("cookbookTitle").textContent = state.recipes.length
    ? `Family cookbook (${state.recipes.length} dish${state.recipes.length === 1 ? "" : "es"})`
    : "Family cookbook";
  return anyBusy;
}

function compareBlock(r) {
  const c = CONDITIONS[r.condition] || CONDITIONS[state.condition];
  const key = r.focus || c.key;
  const meta = NUTRIENTS.find((n) => n[0] === key) || [key, c.nutrient, c.unit];
  const unit = meta[2];
  const before = num(r.original?.nutrition?.[key]);
  const after = num(r.nutrition?.[key]);
  const max = Math.max(before, after, 0.0001);
  const pct = before > 0 ? Math.round(((before - after) / before) * 100) : 0;
  const nutrient = meta[1].toLowerCase();
  let verdict = "";
  if (r.comparable === false) {
    verdict = `<p class="note">The new version uses something that isn't in our food tables yet, so we don't claim a "% less" for this dish.</p>`;
  } else if (pct > 0) {
    verdict = `<p class="win"><span class="win-pct">${pct}%</span><span>less ${esc(nutrient)} per serving, same dish</span></p>`;
  } else {
    verdict = `<p class="note">This dish was already light on ${esc(nutrient)}, so the changes are mostly about cooking habits.</p>`;
  }
  return `
    <div class="compare">
      <p class="compare-title">${esc(meta[1])} per serving <small>${esc(c.plain)}</small></p>
      <div class="ba" role="img" aria-label="${esc(`${meta[1]} per serving: before ${fmt(before, unit)} ${unit}, now ${fmt(after, unit)} ${unit}`)}">
        <span class="ba-label">Before</span>
        <span class="ba-bar"><span style="width:${(before / max) * 100}%"></span></span>
        <span class="ba-val before">${esc(fmt(before, unit))} ${esc(unit)}</span>
        <span class="ba-label now">Now</span>
        <span class="ba-bar now"><span style="width:${Math.max(2, (after / max) * 100)}%"></span></span>
        <span class="ba-val now">${esc(fmt(after, unit))} ${esc(unit)}</span>
      </div>
      ${verdict}
    </div>`;
}

function ingredientsBlock(r) {
  const orig = r.original?.ingredients;
  const unc = new Set(r.nutrition?.uncounted || []);
  const row = (g, extra = "") => {
    const notCounted = g.matched === false || unc.has(g.item) ? `<span class="ing-unc">(not in tables, not counted)</span>` : "";
    return `<li><span>${esc(g.item)}${extra}${notCounted}</span>`;
  };
  if (!orig) {
    return `<ul class="ing-list">${(r.ingredients || []).map((g) => `${row(g)}<span class="ing-g">${esc(grams(g.grams))}</span></li>`).join("")}</ul>`;
  }
  const before = new Map(orig.map((g) => [g.item, num(g.grams)]));
  const nowItems = new Set((r.ingredients || []).map((g) => g.item));
  const items = (r.ingredients || []).map((g) => {
    const was = before.get(g.item);
    if (was === undefined) return `${row(g, `<span class="ing-new">new</span>`)}<span class="ing-g">${esc(grams(g.grams))}</span></li>`;
    if (Math.abs(was - num(g.grams)) > 0.05) return `${row(g)}<span class="ing-g"><span class="ing-was"><span class="sr-only">was </span>${esc(grams(was))}</span><span class="sr-only">now </span>${esc(grams(g.grams))}</span></li>`;
    return `${row(g)}<span class="ing-g">${esc(grams(g.grams))}</span></li>`;
  });
  orig.filter((g) => !nowItems.has(g.item)).forEach((g) => {
    items.push(`<li><span class="ing-gone">${esc(g.item)}</span><span class="ing-g">removed</span></li>`);
  });
  return `<ul class="ing-list">${items.join("")}</ul>`;
}

function sourcesBlock(r) {
  const n = r.nutrition || {};
  const o = r.original?.nutrition;
  const rows = NUTRIENTS.map(([k, label, unit]) => {
    const now = `${unit === "kcal" ? "≈ " : ""}${fmt(n[k], unit)} ${unit}`;
    if (!o) return `<tr><td>${esc(label)}</td><td>${esc(now)}</td></tr>`;
    const down = LOWER_IS_BETTER.has(k) && num(n[k]) < num(o[k]) - 0.05;
    return `<tr><td>${esc(label)}</td><td>${esc(fmt(o[k], unit))} ${esc(unit)}</td><td class="${down ? "down" : ""}">${esc(now)}</td></tr>`;
  }).join("");
  const head = o ? `<tr><th scope="col">Per serving</th><th scope="col">Before</th><th scope="col">Now</th></tr>` : `<tr><th scope="col">Per serving</th><th scope="col">Amount</th></tr>`;
  const sources = (r.sources || []).map((s) => `
    <li><span>${esc(s.item)}<br><span class="muted">${esc(readableRecord(s.record))}</span></span>
      <span class="src-id"><span class="src-tag">${esc(s.source)}</span>${esc(s.id)}</span></li>`).join("");
  const unc = n.uncounted?.length ? `<p class="small-print">Not counted (not in our tables yet): ${esc(n.uncounted.join(", "))}.</p>` : "";
  return `
    <table class="nut-table"><caption class="sr-only">Nutrition per serving</caption><thead>${head}</thead><tbody>${rows}</tbody></table>
    <ul class="src-list">${sources || `<li class="muted">No sources listed.</li>`}</ul>
    ${unc}
    <p class="small-print">Computed by our code from published food tables (IFCT 2017, USDA SR28) using raw weights. The AI doesn't produce these numbers.</p>`;
}

function dishCard(e) {
  const r = current(e);
  const n = r.nutrition || {};
  const c = CONDITIONS[state.condition];
  const adapted = Boolean(e.adapted);
  const meal = r.meal === "dessert" ? "Sweet" : r.meal === "breakfast" ? "Breakfast" : "Main";
  const uncounted = !adapted && n.uncounted?.length
    ? `<p class="warn">Not counted yet (not in our food tables): ${esc(n.uncounted.join(", "))}.</p>` : "";

  let body;
  if (adapted) {
    body = `
      ${compareBlock(r)}
      ${r.changes?.length ? `<div><p class="changes-title">What we changed</p><ul class="changes">${r.changes.map((ch) => `
        <li><span class="tick" aria-hidden="true">✓</span><span>${esc(ch.what)}<span class="why">Why: ${esc(ch.why)}</span></span></li>`).join("")}</ul></div>` : ""}
      ${r.cooking_tip ? `<p class="tip"><b>Cooking tip:</b> ${esc(r.cooking_tip)}</p>` : ""}
      <div class="small-stats">
        <span class="pill">≈ ${esc(fmt(n.kcal, "kcal"))} kcal</span>
        <span class="pill">${esc(fmt(n.protein_g, "g"))} g protein</span>
        <span class="pill">serves ${esc(r.servings)}</span>
      </div>`;
  } else {
    body = `
      <div class="stat-row">
        <span><span class="stat-big">${esc(fmt(n[c.key], c.unit))}</span> <span class="stat-unit">${esc(c.unit)}</span></span>
        <span class="stat-label">${esc(c.nutrient)} per serving now</span>
      </div>
      <div class="small-stats">
        <span class="pill">≈ ${esc(fmt(n.kcal, "kcal"))} kcal</span>
        <span class="pill">${esc(fmt(n.protein_g, "g"))} g protein</span>
        <span class="pill">serves ${esc(r.servings)}</span>
      </div>
      ${uncounted}
      ${e.status === "busy" ? `<p class="working"><span class="spinner" aria-hidden="true"></span><span>Nemotron Super is making it lighter<span class="dots"></span></span></p>` : ""}
      ${e.status === "error" ? `<p class="msg error" role="alert">${esc(e.error)}</p>` : ""}`;
  }

  const action = adapted
    ? `<span class="pill good">Lighter for ${esc(parentWord())}</span><button type="button" class="btn-link" data-undo="${esc(e.id)}">Show original</button>`
    : `<button type="button" class="btn btn-primary btn-small" data-adapt="${esc(e.id)}" ${e.status === "busy" ? "disabled aria-busy=\"true\"" : ""}>${e.status === "error" ? "Try again" : `Make it lighter for ${esc(parentWord())}`}</button>
       <button type="button" class="btn-link" data-remove="${esc(e.id)}" aria-label="Remove ${esc(r.name)}">Remove</button>`;

  return `
    <article class="dish${adapted ? " is-adapted" : ""}" data-card="${esc(e.id)}" aria-busy="${e.status === "busy"}">
      <div class="dish-head">
        <div class="dish-tags"><span class="pill">${esc(meal)}</span>${adapted ? `<span class="pill good">Adapted for ${esc(CONDITIONS[r.condition]?.label.toLowerCase() || "")}</span>` : ""}</div>
        <h3 tabindex="-1">${esc(r.name)}</h3>
        ${e.base.source_text ? `<p class="quote">“${esc(e.base.source_text)}”</p>` : ""}
      </div>
      <div class="dish-body">${body}</div>
      <details class="more"><summary>Ingredients (${esc((r.ingredients || []).length)})${adapted ? " · before and after" : ""}</summary>
        <div class="more-body">${ingredientsBlock(r)}</div></details>
      <details class="more"><summary>Where the numbers come from</summary>
        <div class="more-body">${sourcesBlock(r)}</div></details>
      <div class="dish-actions">${action}</div>
    </article>`;
}

function renderSummary() {
  const done = state.recipes.filter((e) => e.adapted && e.adapted.condition === state.condition);
  if (!done.length) { $("summary").innerHTML = ""; return; }
  const c = CONDITIONS[state.condition];
  const pcts = done.filter((e) => e.adapted.comparable !== false).map((e) => {
    const r = e.adapted; const k = r.focus || c.key;
    const b = num(r.original?.nutrition?.[k]); const a = num(r.nutrition?.[k]);
    return b > 0 ? ((b - a) / b) * 100 : 0;
  });
  const avg = pcts.length ? Math.round(pcts.reduce((s, x) => s + x, 0) / pcts.length) : 0;
  $("summary").innerHTML = avg > 0 ? `
    <div class="summary">
      <span class="summary-big">${avg}% less ${esc(c.nutrient)}</span>
      <span>on average per serving, across ${done.length} of ${state.recipes.length} dish${state.recipes.length === 1 ? "" : "es"}. Same family food, lighter for ${esc(parentWord())}.</span>
    </div>` : "";
}

function renderCookbook() {
  const box = $("cookbook");
  box.innerHTML = state.recipes.length
    ? state.recipes.map(dishCard).join("")
    : `<div class="empty"><p><b>No dishes yet.</b></p><p>Pick a demo family above, or add your first family recipe in step 2.</p></div>`;
  renderSummary();
  refreshButtons();
}

// Replace one card in place, keeping focus sensible for keyboard users.
function renderCard(id) {
  const e = findEntry(id);
  const old = document.querySelector(`[data-card="${CSS.escape(id)}"]`);
  if (!e || !old) { renderCookbook(); return; }
  const hadFocus = old.contains(document.activeElement);
  const tmp = document.createElement("div");
  tmp.innerHTML = dishCard(e).trim();
  const card = tmp.firstElementChild;
  old.replaceWith(card);
  if (hadFocus) {
    const target = card.querySelector("[data-adapt]:not([disabled])") || card.querySelector("h3");
    target?.focus({ preventScroll: true });
  }
  renderSummary();
  refreshButtons();
}

async function adaptOne(id) {
  const e = findEntry(id);
  if (!e || e.adapted || e.status === "busy") return "skip";
  const condition = state.condition;
  e.status = "busy"; e.error = "";
  renderCard(id);
  try {
    const { recipe } = await api("/api/adapt", { recipe: baseFields(e.base), condition, cuisine: state.cuisine });
    // Drop the reply if the dish was removed/replaced or the health focus changed meanwhile.
    if (findEntry(id) !== e || state.condition !== condition) return "stale";
    if (recipe.condition && recipe.condition !== condition) return "stale";
    e.adapted = { ...recipe, condition, id: e.id };
    e.status = "idle";
    if (state.plan) state.planStale = true;
    renderCard(id);
    renderPlanStale();
    return "ok";
  } catch (err) {
    if (findEntry(id) !== e || state.condition !== condition) return "stale";
    e.status = "error"; e.error = err.message;
    renderCard(id);
    return "fail";
  }
}

async function adaptAll(btn) {
  const run = ++state.adaptRun;
  const ids = state.recipes.filter((e) => !e.adapted && e.status !== "busy").map((e) => e.id);
  if (!ids.length) return;
  const prog = $("adaptProgress");
  let done = 0, failed = 0, i = 0;
  const draw = () => {
    if (run !== state.adaptRun) return;
    prog.hidden = false;
    prog.className = "progress-line";
    prog.textContent = `Making ${ids.length} dish${ids.length === 1 ? "" : "es"} lighter… ${done} of ${ids.length} done${failed ? `, ${failed} couldn't be changed` : ""}.`;
  };
  draw();
  await busy(btn, "Working…", async () => {
    const worker = async () => {
      while (i < ids.length && run === state.adaptRun) {
        const id = ids[i++];
        const result = await adaptOne(id);
        if (result === "fail") failed += 1; else done += 1;
        draw();
      }
    };
    await Promise.all(Array.from({ length: Math.min(ADAPT_CONCURRENCY, ids.length) }, worker));
  });
  if (run !== state.adaptRun) return;
  const ok = ids.length - failed;
  prog.className = failed ? "progress-line has-fail" : "progress-line done";
  prog.textContent = failed
    ? `${ok} of ${ids.length} dishes made lighter. ${failed} couldn't be changed: tap "Try again" on ${failed === 1 ? "that dish" : "those dishes"}.`
    : `All ${ids.length} dishes are lighter for ${parentWord()}. Next: make your week below.`;
  announce(prog.textContent);
}

// ---------- add a recipe ----------
async function parseRecipe(btn) {
  const text = $("recipeText").value.trim();
  const msg = $("parseMsg");
  msg.className = "msg";
  if (text.length < 3) {
    msg.className = "msg error";
    msg.textContent = "Type or say a recipe first: the dish name, then what goes in.";
    $("recipeText").focus();
    return;
  }
  const servings = Math.min(20, Math.max(1, Math.round(num($("servings").value) || 4)));
  const stop = ticker(msg, (s) => `Nemotron Nano is reading your recipe and matching it to food tables<span class="dots"></span>${s >= 2 ? ` ${s}s` : ""}`);
  try {
    const { recipe } = await busy(btn, "Reading…", () => api("/api/parse", { text, servings, cuisine: state.cuisine }));
    stop();
    const id = uid();
    state.recipes.unshift({ id, base: { ...recipe, id }, adapted: null, status: "idle", error: "" });
    if (state.plan) state.planStale = true;
    $("recipeText").value = "";
    msg.className = "msg ok";
    const unc = recipe.nutrition?.uncounted?.length;
    msg.textContent = `Added “${recipe.name}” with ${recipe.ingredients.length} ingredients${unc ? ` (${unc} not in our food tables yet)` : ""}. It's at the top of your cookbook.`;
    renderCookbook();
    renderPlanStale();
  } catch (err) {
    stop();
    msg.className = "msg error";
    msg.textContent = err.message;
  }
}

// ---------- voice ----------
const voice = { rec: null, listening: false };

function updateMicHint() {
  if (!voice.rec) return;
  const code = SPEECH_LANG[state.language] || "en-IN";
  $("micHint").hidden = false;
  $("micHint").textContent = `Voice typing listens in ${state.language} (${code}). The words appear in the box so you can fix anything before reading the recipe.`;
}

function setupVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("mic");
  if (!SR) return; // button stays hidden where the browser can't do voice typing
  let rec;
  try { rec = new SR(); } catch { return; }
  voice.rec = rec;
  mic.hidden = false;
  rec.interimResults = false;
  rec.continuous = false;
  rec.maxAlternatives = 1;
  const label = mic.querySelector(".mic-label");
  const setListening = (on) => {
    voice.listening = on;
    mic.setAttribute("aria-pressed", String(on));
    label.textContent = on ? "Listening… tap to stop" : "Speak it";
  };
  rec.onresult = (ev) => {
    const box = $("recipeText");
    const said = Array.from(ev.results).map((r) => r[0]?.transcript || "").join(" ").trim();
    if (said) box.value = (box.value.trim() ? box.value.trim() + " " : "") + said;
  };
  rec.onerror = (ev) => {
    const m = $("parseMsg");
    const reasons = {
      "not-allowed": "Microphone access was blocked. Allow it in your browser settings, or type instead.",
      "service-not-allowed": "Voice typing isn't available here. Please type instead.",
      "no-speech": "We didn't hear anything. Tap Speak it and try again.",
      "audio-capture": "No microphone found. Please type instead.",
      "network": "Voice typing needs an internet connection. Please type instead.",
      "language-not-supported": `Voice typing doesn't support ${state.language} in this browser. Try English, or type instead.`,
    };
    if (ev.error !== "aborted") { m.className = "msg error"; m.textContent = reasons[ev.error] || "Voice typing stopped. Please try again or type instead."; }
    setListening(false);
  };
  rec.onend = () => setListening(false);
  mic.addEventListener("click", () => {
    if (voice.listening) { try { rec.stop(); } catch { /* already stopped */ } return; }
    rec.lang = SPEECH_LANG[state.language] || "en-IN";
    try {
      rec.start();
      setListening(true);
    } catch (err) {
      // InvalidStateError: a session is still closing. Reset quietly and let the user tap again.
      try { rec.abort(); } catch { /* ignore */ }
      setListening(false);
    }
  });
  updateMicHint();
}

// ---------- week ----------
function renderPlanStale() {
  const el = document.querySelector("#planOut .stale");
  if (el) el.hidden = !state.planStale;
}

function dishLabel(name, slot) {
  if (!name) return `<span class="none">${slot === "dessert" ? "No sweet today" : "Your choice"}</span>`;
  const e = state.recipes.find((x) => current(x).name === name);
  return `${esc(name)}${e?.adapted ? `<span class="lite">lighter</span>` : ""}`;
}

function renderPlan() {
  const out = $("planOut");
  const plan = state.plan;
  if (!plan) { out.innerHTML = ""; return; }
  const slots = [["breakfast", "Breakfast"], ["lunch", "Lunch"], ["dinner", "Dinner"], ["dessert", "Sweet treat"]];
  const days = plan.days || [];
  const groups = {};
  (plan.shopping_list || []).forEach((s) => { (groups[s.category in SHOP_GROUPS ? s.category : "other"] ||= []).push(s); });
  const unadapted = state.recipes.filter((e) => !e.adapted).length;

  out.innerHTML = `
    <p class="msg error stale" ${state.planStale ? "" : "hidden"}>Your cookbook changed since this plan was made. Tap "Make our week" again to include the changes.</p>
    ${unadapted ? `<p class="hint">${unadapted} dish${unadapted === 1 ? " is" : "es are"} still the original version. Make ${unadapted === 1 ? "it" : "them"} lighter first, then remake the week.</p>` : ""}
    <div class="letter">
      <p class="letter-label">A note for ${esc(parentWord())} · ${esc(plan.language)}</p>
      <p class="letter-text" id="parentMsg">${esc(plan.message_for_parent)}</p>
      <div class="copy-row"><button type="button" class="btn btn-quiet btn-small" data-copy="parentMsg">Copy the note</button>
        <span class="muted">Paste it into WhatsApp or a text message.</span></div>
    </div>

    <ol class="week-cards" aria-label="Meals for the week">
      ${days.map((d) => `<li class="day"><h3>${esc(DAY_NAMES[d.day] || d.day)}</h3><dl>
        ${slots.map(([k, l]) => `<dt>${l}</dt><dd>${dishLabel(d[k], k)}</dd>`).join("")}</dl></li>`).join("")}
    </ol>
    <div class="week-table-wrap">
      <table class="week-table">
        <caption class="sr-only">Meals for the week</caption>
        <thead><tr><th scope="col">Day</th>${slots.map(([, l]) => `<th scope="col">${l}</th>`).join("")}</tr></thead>
        <tbody>${days.map((d) => `<tr><th scope="row">${esc(DAY_NAMES[d.day] || d.day)}</th>${slots.map(([k]) => `<td>${dishLabel(d[k], k)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>

    <div class="week-cols">
      <section class="panel" aria-labelledby="shopTitle">
        <h3 id="shopTitle">Shopping list for the week</h3>
        <p class="hint small">Raw weights for every dish in the plan. Tick things off as you shop.</p>
        ${Object.keys(SHOP_GROUPS).filter((k) => groups[k]).map((k) => `
          <div class="shop-group"><h4>${esc(SHOP_GROUPS[k])}</h4>
            <ul class="shop">${groups[k].map((s) => `<li><label><input type="checkbox"><span class="shop-item"><span>${esc(s.item)}</span><span class="shop-qty">${esc(grams(s.grams))}</span></span></label></li>`).join("")}</ul>
          </div>`).join("")}
        <div class="copy-row" style="margin-top:14px"><button type="button" class="btn btn-quiet btn-small" data-copy="shop">Copy the list</button></div>
      </section>
      <section class="panel" aria-labelledby="tipsTitle">
        <h3 id="tipsTitle">Tips for the week</h3>
        <ul class="tips">${(plan.tips || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
      </section>
    </div>`;
}

async function makePlan(btn) {
  const out = $("planOut");
  const holder = document.createElement("p");
  holder.className = "working";
  out.prepend(holder);
  const stop = ticker(holder, (s) => `<span class="spinner" aria-hidden="true"></span><span>Nemotron Ultra is planning 7 days and the shopping list<span class="dots"></span>${s >= 2 ? ` ${s}s` : ""}</span>`);
  const condition = state.condition;
  try {
    const recipes = state.recipes.map((e) => baseFields(current(e)));
    const { plan } = await busy(btn, "Planning…", () => api("/api/plan", { recipes, condition, language: state.language }));
    stop();
    if (state.condition !== condition) { holder.remove(); return; }
    state.plan = plan; state.planStale = false;
    renderPlan();
    $("s4").focus({ preventScroll: true });
    announce("Your week is ready, with a shopping list and a note for your parent.");
  } catch (err) {
    stop();
    holder.className = "msg error";
    holder.setAttribute("role", "alert");
    holder.textContent = err.message;
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

// ---------- events ----------
document.querySelectorAll('input[name="condition"]').forEach((r) => r.addEventListener("change", () => setCondition(r.value)));
$("cuisine").addEventListener("change", (e) => { state.cuisine = e.target.value; syncControls(); });
$("language").addEventListener("change", (e) => { state.language = e.target.value; updateMicHint(); });
$("parentName").addEventListener("input", (e) => {
  state.parentName = e.target.value.slice(0, 20);
  clearTimeout(state._nameTimer);
  state._nameTimer = setTimeout(() => { renderCookbook(); if (state.plan) renderPlan(); }, 400);
});

$("families").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-family]");
  if (btn) loadFamily(btn.dataset.family, btn);
});

$("startOwn").addEventListener("click", () => {
  const hadDemo = Boolean(state.family);
  state.adaptRun += 1;
  if (hadDemo) {
    state.family = null; state.recipes = []; state.plan = null; state.parentName = "";
    $("adaptProgress").hidden = true;
    renderFamilies(); renderCookbook(); renderPlan(); syncControls();
  }
  $("s1").scrollIntoView({ block: "start" });
  $("s1").focus({ preventScroll: true });
  announce(hadDemo ? "Cleared the demo dishes. Tell us who you're cooking for, then add your first recipe." : "Tell us who you're cooking for, then add your first recipe.");
});

document.querySelectorAll(".stepper-btn").forEach((b) => b.addEventListener("click", () => {
  const input = $("servings");
  input.value = Math.min(20, Math.max(1, (Math.round(num(input.value)) || 4) + Number(b.dataset.step)));
}));

$("parse").addEventListener("click", (e) => parseRecipe(e.currentTarget));
$("recipeText").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("parse").click(); }
});

$("cookbook").addEventListener("click", (e) => {
  const a = e.target.closest("[data-adapt]");
  if (a) { adaptOne(a.dataset.adapt); return; }
  const u = e.target.closest("[data-undo]");
  if (u) {
    const entry = findEntry(u.dataset.undo);
    if (entry) {
      entry.adapted = null; entry.status = "idle";
      if (state.plan) state.planStale = true;
      renderCard(entry.id); renderPlanStale();
      announce(`${entry.base.name}: showing the original recipe.`);
    }
    return;
  }
  const rm = e.target.closest("[data-remove]");
  if (rm) {
    const entry = findEntry(rm.dataset.remove);
    state.recipes = state.recipes.filter((x) => x.id !== rm.dataset.remove);
    if (state.plan) state.planStale = true;
    renderCookbook(); renderPlanStale();
    $("s3").focus({ preventScroll: true });
    if (entry) announce(`Removed ${entry.base.name}.`);
  }
});

$("adaptAll").addEventListener("click", (e) => adaptAll(e.currentTarget));
$("plan").addEventListener("click", (e) => makePlan(e.currentTarget));

$("planOut").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  let text = "";
  if (b.dataset.copy === "parentMsg") text = state.plan?.message_for_parent || "";
  else text = (state.plan?.shopping_list || []).map((s) => `${s.item}: ${grams(s.grams)}`).join("\n");
  const ok = await copyText(text);
  toast(ok ? "Copied. Paste it anywhere." : "Couldn't copy. Please select the text and copy it.");
});

// ---------- start ----------
async function init() {
  fillSelects();
  renderCookbook();
  renderTiers();
  setupVoice();
  try {
    const h = await api("/api/health");
    state.health = h;
    const b = $("mode");
    const live = h.mode === "live";
    b.textContent = live ? "Live: Nemotron on Nebius" : "Demo mode";
    b.title = live ? "Real Nemotron models on Nebius Token Factory" : "Runs without an API key using built-in sample answers. Numbers are still computed from the food tables.";
    b.classList.toggle("live", live);
    fillSelects();
    renderTiers();
  } catch {
    const b = $("mode");
    b.textContent = "Server offline";
    b.classList.add("off");
  }
  try {
    state.families = await api("/api/demo");
  } catch { state.families = []; }
  renderFamilies();
}

init();
