// Heritage Plate front end: plain JS, no build step, no external dependencies.
"use strict";

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// ---------- constants ----------
// `nutrient` is the plain-words name shown next to every number.
const CONDITIONS = {
  diabetes: {
    label: "Type 2 diabetes", short: "Diabetes", key: "net_carbs_g", nutrient: "sugar-raising carbs", unit: "g",
    hint: "We lower the carbs that raise blood sugar.",
  },
  bp: {
    label: "High blood pressure", short: "Blood pressure", key: "sodium_mg", nutrient: "salt (sodium)", unit: "mg",
    hint: "We lower salt (sodium), mostly from salt and salty sauces.",
  },
  cholesterol: {
    label: "High cholesterol", short: "Cholesterol", key: "sat_fat_g", nutrient: "saturated fat", unit: "g",
    hint: "We lower saturated fat, mostly from ghee, butter, cream and fatty meat.",
  },
};

const NUTRIENTS = [
  ["kcal", "Energy", "kcal"],
  ["net_carbs_g", "Sugar-raising carbs", "g"],
  ["fiber_g", "Fibre", "g"],
  ["protein_g", "Protein", "g"],
  ["fat_g", "Fat", "g"],
  ["sat_fat_g", "Saturated fat", "g"],
  ["sodium_mg", "Salt (sodium)", "mg"],
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
const MODELS = {
  nano: { name: "Nemotron Nano", job: "Reads your recipe into ingredients and grams." },
  super: { name: "Nemotron Super", job: "Suggests swaps that keep the dish familiar." },
  ultra: { name: "Nemotron Ultra", job: "Plans the week and writes the note." },
};
const ADAPT_CONCURRENCY = 3;
const MAX_DISHES = 30; // matches the /api/plan limit
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
  started: false,        // a family was picked or "use your own recipes" was chosen
  own: false,
  family: null,          // {id, family, parent, ...} when a demo family is loaded
  families: [],
  familiesLoaded: false,
  recipes: [],           // [{id, base, adapted, status: idle|busy|error, error, open}]
  trace: [],
  health: null,
  plan: null,
  planStale: false,
  weekTab: "meals",
  adaptRun: 0,           // bumps to cancel a running "make every dish lighter"
  cookbookVersion: 0,    // bumps whenever the dishes change; late /api/plan replies are dropped
};

function markCookbookChanged() {
  state.cookbookVersion += 1;
  if (state.plan) state.planStale = true;
}

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

function scrollToEl(el) {
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
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
// The message is written once (announced once); only an aria-hidden seconds counter updates.
function ticker(el, html) {
  const start = Date.now();
  el.innerHTML = `${html} <span class="secs" aria-hidden="true"></span>`;
  const secs = el.querySelector(".secs");
  const t = setInterval(() => {
    const s = Math.floor((Date.now() - start) / 1000);
    if (s >= 2) secs.textContent = `${s}s`;
  }, 1000);
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
  $("tiers").innerHTML = Object.entries(MODELS).map(([k, t]) => `
    <div class="tier">
      <p class="tier-name">${esc(t.name)}</p>
      <p class="tier-job">${esc(t.job)}</p>
      ${models[k] ? `<code>${esc(models[k])}</code>` : ""}
      <p class="tier-count">${counts[k]} call${counts[k] === 1 ? "" : "s"} so far</p>
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
    return `<li><b>${esc(t.step)}</b> <span class="muted">· ${esc(MODELS[tier].name)}</span>${bits.length ? ` <span class="muted">· ${esc(bits.join(", "))}</span>` : ""}${flags.length ? ` <span class="tflag">(${esc(flags.join(", "))})</span>` : ""}<br><code>${esc(t.model)}</code></li>`;
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
  $("focusHint").textContent = CONDITIONS[state.condition].hint;
  renderNames();
  updateMicHint();
}

// Everywhere the parent's name or language shows, without re-rendering the dish cards.
function renderNames() {
  $("aboutSummary").innerHTML = `For <b>${esc(parentWord())}</b> · note in ${esc(state.language)}`;
  document.querySelectorAll(".parent-word").forEach((el) => { el.textContent = parentWord(); });
}

function setCondition(value) {
  if (!(value in CONDITIONS) || value === state.condition) return;
  state.condition = value;
  state.adaptRun += 1; // stop any running batch; late replies for the old condition are dropped
  let reset = 0;
  state.recipes.forEach((e) => {
    if (e.adapted || e.status !== "idle") reset += 1;
    e.adapted = null; e.status = "idle"; e.error = ""; e.open = false;
  });
  $("adaptProgress").hidden = true;
  markCookbookChanged();
  syncControls();
  renderCookbook();
  renderPlan();
  announce(`Now cooking for ${CONDITIONS[value].label}.${reset ? " Dishes are back to their originals; make them lighter again." : ""}`);
}

// ---------- steps ----------
function stepState() {
  const n = state.recipes.length;
  const allLighter = n > 0 && state.recipes.every((e) => e.adapted);
  const done = { 1: state.started, 2: allLighter, 3: Boolean(state.plan && !state.planStale) };
  const unlocked = { 1: true, 2: state.started, 3: n > 0 };
  let currentStep = 3;
  for (const s of [1, 2, 3]) { if (!done[s]) { currentStep = s; break; } }
  return { done, unlocked, currentStep };
}

function renderSteps() {
  const { done, unlocked, currentStep } = stepState();
  $("stepDishes").hidden = !unlocked[2];
  $("stepWeek").hidden = !unlocked[3];
  document.querySelectorAll("[data-goto]").forEach((b) => {
    const s = Number(b.dataset.goto);
    b.disabled = !unlocked[s];
    b.classList.toggle("is-done", done[s]);
    if (s === currentStep) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    const n = b.querySelector(".step-n");
    n.textContent = done[s] ? "✓" : String(s);
    b.setAttribute("aria-label", `Step ${s}: ${b.textContent.replace(/^[✓\d]/, "").trim()}${done[s] ? ", done" : unlocked[s] ? "" : ", not yet"}`);
  });
}

function goToStep(s) {
  const heading = $(`s${s}`);
  const sec = s === 1 ? $("start") : s === 2 ? $("stepDishes") : $("stepWeek");
  if (!heading || sec.hidden) return;
  scrollToEl(sec);
  heading.focus({ preventScroll: true });
}

// ---------- families ----------
function renderFamilies() {
  const box = $("families");
  if (!state.families.length) {
    box.innerHTML = state.familiesLoaded
      ? `<div class="empty"><p>The demo families couldn't load.</p><button type="button" class="btn btn-quiet btn-small" data-retry>Try again</button></div>`
      : box.innerHTML;
    return;
  }
  box.innerHTML = state.families.map((f, i) => {
    const initial = (f.family || "?").replace(/^The\s+/i, "").charAt(0).toUpperCase();
    const who = String(f.parent || "").split(/[,(]/)[0].trim();
    const on = state.family?.id === f.id;
    return `
      <button type="button" class="family" data-family="${esc(f.id)}" aria-pressed="${on}">
        <span class="avatar" style="background:${FAMILY_COLORS[i % FAMILY_COLORS.length]}" aria-hidden="true">${esc(initial)}</span>
        <span class="family-text">
          <span class="family-name">${esc(String(f.family || "").replace(/^The\s+/i, "").replace(/\s+family$/i, ""))} family</span>
          <span class="family-meta">${esc(who)} · ${esc(CONDITIONS[f.condition]?.short || f.condition)}</span>
          <span class="family-sub">${esc(shortCuisine(f.cuisine))} · ${esc(f.language)}</span>
        </span>
        <span class="family-check" aria-hidden="true">${on ? "✓" : ""}</span>
      </button>`;
  }).join("");
}

async function loadFamily(id, btn) {
  btn.classList.add("is-loading");
  btn.setAttribute("aria-busy", "true");
  const check = btn.querySelector(".family-check");
  if (check) check.innerHTML = `<span class="spinner" aria-hidden="true"></span>`;
  try {
    const fam = await api(`/api/demo/${encodeURIComponent(id)}`);
    state.adaptRun += 1;
    state.family = fam;
    state.started = true; state.own = false;
    state.condition = fam.condition in CONDITIONS ? fam.condition : "diabetes";
    state.cuisine = fam.cuisine;
    state.language = fam.language;
    state.parentName = String(fam.parent || "").split(",")[0].trim().slice(0, 20);
    state.recipes = (fam.recipes || []).map((r) => ({ id: String(r.id || uid()), base: r, adapted: null, status: "idle", error: "", open: false }));
    state.plan = null; state.planStale = false; state.cookbookVersion += 1;
    $("adaptProgress").hidden = true;
    $("parseMsg").textContent = "";
    $("addBox").open = false;
    $("about").open = false;
    $("startOwn").setAttribute("aria-pressed", "false");
    syncControls();
    renderFamilies();
    renderCookbook();
    renderPlan();
    goToStep(2);
    announce(`Loaded ${fam.family}: ${state.recipes.length} dishes, cooking for ${fam.parent}.`);
  } catch (err) {
    renderFamilies();
    toast(err.message);
  }
}

// ---------- cookbook ----------
function refreshButtons() {
  const n = state.recipes.length;
  const anyBusy = state.recipes.some((e) => e.status === "busy");
  const todo = state.recipes.some((e) => !e.adapted && e.status !== "busy");
  const allLighter = n > 0 && state.recipes.every((e) => e.adapted);
  $("adaptBar").hidden = n === 0;
  const all = $("adaptAll");
  if (!all.hasAttribute("aria-busy")) {
    all.disabled = !todo;
    const finished = n && !todo && !anyBusy;
    all.textContent = finished ? "✓ Every dish is lighter" : "Make every dish lighter";
    all.classList.toggle("btn-primary", !finished);
    all.classList.toggle("btn-done", Boolean(finished));
  }
  const plan = $("plan");
  if (!plan.hasAttribute("aria-busy")) {
    plan.disabled = n === 0;
    const fresh = state.plan && !state.planStale;
    plan.textContent = state.plan ? (state.planStale ? "Update our week" : "Plan again") : "Plan our week";
    // One loud button at a time: the week button gets loud once the dishes are done.
    const loud = !fresh && (allLighter || state.planStale || (!todo && !anyBusy));
    plan.classList.toggle("btn-primary", Boolean(loud));
    plan.classList.toggle("btn-quiet", !loud);
  }
  renderSteps();
  return anyBusy;
}

function focusNumbers(r) {
  const c = CONDITIONS[r.condition] || CONDITIONS[state.condition];
  const key = r.focus || c.key;
  const meta = NUTRIENTS.find((x) => x[0] === key) || [key, c.nutrient, c.unit];
  const before = num(r.original?.nutrition?.[key]);
  const after = num(r.nutrition?.[key]);
  const pct = before > 0 ? Math.round(((before - after) / before) * 100) : 0;
  return { unit: meta[2], label: c.nutrient, before, after, pct };
}

function ingredientsBlock(r) {
  const orig = r.original?.ingredients;
  const unc = new Set(r.nutrition?.uncounted || []);
  const row = (g, extra = "") => {
    const notCounted = g.matched === false || unc.has(g.item) ? `<span class="ing-unc">not counted</span>` : "";
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
      <span class="src-id">${esc(s.source)} ${esc(s.id)}</span></li>`).join("");
  const unc = n.uncounted?.length ? `<p class="small-print">Not counted (not in our tables yet): ${esc(n.uncounted.join(", "))}.</p>` : "";
  return `
    <table class="nut-table"><caption class="sr-only">Nutrition per serving</caption><thead>${head}</thead><tbody>${rows}</tbody></table>
    <ul class="src-list">${sources || `<li class="muted">No sources listed.</li>`}</ul>
    ${unc}
    <p class="small-print">Worked out by our code from food tables, using raw weights. Not by the AI.</p>`;
}

function dishCard(e) {
  const r = current(e);
  const n = r.nutrition || {};
  const c = CONDITIONS[state.condition];
  const adapted = Boolean(e.adapted);
  const meal = r.meal === "dessert" ? "Sweet" : r.meal === "breakfast" ? "Breakfast" : "Main";
  const isBusy = e.status === "busy";

  let numbers, badge = "";
  if (adapted) {
    const f = focusNumbers(r);
    const width = f.before > 0 ? Math.max(3, Math.min(100, (f.after / f.before) * 100)) : 100;
    numbers = `
      <p class="nums"><span class="sr-only">${esc(f.label)} per serving: was </span><span class="nums-was">${esc(fmt(f.before, f.unit))}</span><span class="nums-arrow" aria-hidden="true">→</span><span class="sr-only"> now </span><span class="nums-now">${esc(fmt(f.after, f.unit))} ${esc(f.unit)}</span></p>
      <p class="nums-label" aria-hidden="true">${esc(f.label)} per serving</p>
      <span class="bar" aria-hidden="true"><span style="width:${width}%"></span></span>`;
    if (r.comparable === false) badge = `<span class="tag tag-quiet">No % shown</span>`;
    else if (f.pct > 0) badge = `<span class="tag tag-win">${f.pct}% less</span>`;
    else badge = `<span class="tag tag-quiet">Already light</span>`;
  } else {
    numbers = `
      <p class="nums"><span class="nums-now plain">${esc(fmt(n[c.key], c.unit))} ${esc(c.unit)}</span></p>
      <p class="nums-label">${esc(c.nutrient)} per serving</p>`;
  }

  let status = "";
  if (isBusy) status = `<p class="working"><span class="spinner" aria-hidden="true"></span><span>Making it lighter<span class="dots"></span></span></p>`;
  else if (e.status === "error") status = `<p class="msg error" role="alert">${esc(e.error)}</p>`;

  const adaptBtn = adapted ? "" : `
    <button type="button" class="btn btn-quiet btn-small" data-adapt="${esc(e.id)}" ${isBusy ? "disabled aria-busy=\"true\"" : ""}>${e.status === "error" ? "Try again" : "Make it lighter"}</button>`;

  let detail;
  if (adapted) {
    const why = r.comparable === false
      ? `<p class="small-print">The new version uses something not in our food tables, so we don't claim a "% less".</p>` : "";
    detail = `
      ${r.changes?.length ? `<ul class="changes">${r.changes.map((ch) => `
        <li><span class="tick" aria-hidden="true">✓</span><span>${esc(ch.what)}<span class="why">${esc(ch.why)}</span></span></li>`).join("")}</ul>` : ""}
      ${r.cooking_tip ? `<p class="tip"><b>Tip:</b> ${esc(r.cooking_tip)}</p>` : ""}
      ${why}
      <h4 class="more-h">Ingredients, before and after</h4>
      ${ingredientsBlock(r)}
      <details class="sub"><summary>Where the numbers come from</summary>${sourcesBlock(r)}</details>
      <button type="button" class="btn-link" data-undo="${esc(e.id)}">Show the original</button>`;
  } else {
    const unc = n.uncounted?.length ? `<p class="small-print">Not counted yet (not in our tables): ${esc(n.uncounted.join(", "))}.</p>` : "";
    detail = `
      ${e.base.source_text ? `<p class="quote">“${esc(e.base.source_text)}”</p>` : ""}
      <h4 class="more-h">Ingredients · serves ${esc(r.servings)}</h4>
      ${ingredientsBlock(r)}
      ${unc}
      <details class="sub"><summary>Where the numbers come from</summary>${sourcesBlock(r)}</details>
      <button type="button" class="btn-link danger" data-remove="${esc(e.id)}" aria-label="Remove ${esc(r.name)}">Remove this dish</button>`;
  }

  return `
    <article class="dish${adapted ? " is-adapted" : ""}" data-card="${esc(e.id)}" aria-busy="${isBusy}">
      <div class="dish-main">
        <div class="dish-top">
          <p class="dish-meal">${esc(meal)}</p>
          ${badge}
        </div>
        <h3 tabindex="-1">${esc(r.name)}</h3>
        ${numbers}
        ${status}
        ${adaptBtn}
      </div>
      <div class="dish-foot">
        <details class="more" data-more="${esc(e.id)}" ${e.open ? "open" : ""}>
          <summary>${adapted ? "See what changed" : "See the recipe"}</summary>
          <div class="more-body">${detail}</div>
        </details>
      </div>
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
      <span class="summary-big">${avg}% less</span>
      <span class="summary-text">${esc(c.nutrient)} on average<br><span class="muted">${done.length} of ${state.recipes.length} dish${state.recipes.length === 1 ? "" : "es"}, same family food</span></span>
    </div>` : "";
}

function renderCookbook() {
  const box = $("cookbook");
  box.innerHTML = state.recipes.length
    ? state.recipes.map(dishCard).join("")
    : `<div class="empty"><p><b>No dishes yet.</b> Add your first family recipe below.</p></div>`;
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
  const token = {};
  e.req = token;
  e.status = "busy"; e.error = "";
  renderCard(id);
  const stale = () => findEntry(id) !== e || state.condition !== condition || e.req !== token;
  try {
    const { recipe } = await api("/api/adapt", { recipe: baseFields(e.base), condition, cuisine: state.cuisine });
    // Drop the reply if the dish was removed/replaced, the health focus changed, or a newer request started.
    if (stale()) return "stale";
    if (recipe.condition && recipe.condition !== condition) return "stale";
    e.adapted = { ...recipe, condition, id: e.id };
    e.status = "idle"; e.open = false;
    markCookbookChanged();
    renderCard(id);
    renderPlanStale();
    return "ok";
  } catch (err) {
    if (stale()) return "stale";
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
    prog.textContent = `${done} of ${ids.length} dishes done${failed ? `, ${failed} couldn't be changed` : ""}…`;
  };
  draw();
  await busy(btn, "Making them lighter…", async () => {
    const worker = async () => {
      while (i < ids.length && run === state.adaptRun) {
        const id = ids[i++];
        const result = await adaptOne(id);
        if (result === "fail") failed += 1; else done += 1;
        draw();
      }
    };
    // Release the button as soon as the run is cancelled (family switch, condition change),
    // instead of waiting up to a minute for old in-flight replies.
    const finished = Promise.all(Array.from({ length: Math.min(ADAPT_CONCURRENCY, ids.length) }, worker));
    let poll;
    const cancelled = new Promise((resolve) => {
      poll = setInterval(() => { if (run !== state.adaptRun) resolve(); }, 200);
    });
    await Promise.race([finished, cancelled]).finally(() => clearInterval(poll));
  });
  if (run !== state.adaptRun) return;
  const ok = ids.length - failed;
  if (failed) {
    prog.className = "progress-line has-fail";
    prog.textContent = `${ok} of ${ids.length} dishes are lighter. Tap "Try again" on the ${failed === 1 ? "other one" : `other ${failed}`}.`;
    announce(prog.textContent);
  } else {
    // The done button and the summary already say it; keep the screen quiet.
    prog.hidden = true;
    announce(`All ${ids.length} dishes are lighter. Next: plan the week.`);
  }
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
  if (state.recipes.length >= MAX_DISHES) {
    msg.className = "msg error";
    msg.textContent = `The cookbook holds up to ${MAX_DISHES} dishes. Remove one to add another.`;
    return;
  }
  const stop = ticker(msg, `<span class="spinner" aria-hidden="true"></span><span>Reading your recipe<span class="dots"></span></span>`);
  msg.className = "msg working";
  try {
    const { recipe } = await busy(btn, "Reading…", () => api("/api/parse", { text, servings, cuisine: state.cuisine }));
    stop();
    const id = uid();
    state.recipes.unshift({ id, base: { ...recipe, id }, adapted: null, status: "idle", error: "", open: false });
    markCookbookChanged();
    $("recipeText").value = "";
    msg.className = "msg ok";
    const unc = recipe.nutrition?.uncounted?.length;
    msg.textContent = `Added “${recipe.name}” to the top of the list${unc ? ` (${unc} ingredient${unc === 1 ? "" : "s"} not counted)` : ""}.`;
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
  $("micHint").hidden = false;
  $("micHint").textContent = `Voice typing listens in ${state.language}. Check the words before adding.`;
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
  refreshButtons();
}

function dishLabel(name) {
  if (!name) return `<span class="none">Your choice</span>`;
  const e = state.recipes.find((x) => current(x).name === name);
  // Lighter is the normal case, so only flag the exceptions.
  return `${esc(name)}${e && !e.adapted ? ` <span class="orig">original</span>` : ""}`;
}

const WEEK_TABS = [["meals", "Meals"], ["shop", "Shopping list"], ["tips", "Tips"]];

function renderPlan() {
  const out = $("planOut");
  const plan = state.plan;
  renderNames();
  if (!plan) { out.innerHTML = ""; refreshButtons(); return; }
  const slots = [["breakfast", "Breakfast"], ["lunch", "Lunch"], ["dinner", "Dinner"], ["dessert", "Sweet"]];
  const days = plan.days || [];
  const groups = {};
  const shopping = plan.shopping_list || [];
  shopping.forEach((s) => { (groups[s.category in SHOP_GROUPS ? s.category : "other"] ||= []).push(s); });
  const unadapted = state.recipes.filter((e) => !e.adapted).length;
  const tab = WEEK_TABS.some(([k]) => k === state.weekTab) ? state.weekTab : "meals";

  const meals = `<ol class="days" aria-label="Meals for the week">
    ${days.map((d) => `<li class="day"><h4 class="day-name">${esc(DAY_NAMES[d.day] || d.day)}</h4><dl class="day-meals">
      ${slots.filter(([k]) => k !== "dessert" || d[k]).map(([k, l]) => `<div><dt>${l}</dt><dd>${dishLabel(d[k])}</dd></div>`).join("")}</dl></li>`).join("")}
  </ol>`;
  const shop = `
    <div class="panel-head"><p class="muted">Raw weights for the whole week. Tick as you shop.</p>
      <button type="button" class="btn btn-quiet btn-small" data-copy="shop">Copy list</button></div>
    ${Object.keys(SHOP_GROUPS).filter((k) => groups[k]).map((k) => `
      <div class="shop-group"><h4>${esc(SHOP_GROUPS[k])}</h4>
        <ul class="shop">${groups[k].map((s) => `<li><label><input type="checkbox"><span class="shop-item"><span>${esc(s.item)}</span><span class="shop-qty">${esc(grams(s.grams))}</span></span></label></li>`).join("")}</ul>
      </div>`).join("")}`;
  const tips = `<ul class="tips">${(plan.tips || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
  const panels = { meals, shop, tips };

  out.innerHTML = `
    <p class="msg warn stale" ${state.planStale ? "" : "hidden"}>Your dishes changed. Tap "Update our week" to include them.</p>
    ${unadapted ? `<p class="hint">${unadapted} dish${unadapted === 1 ? " is" : "es are"} still the original. Make ${unadapted === 1 ? "it" : "them"} lighter, then plan again.</p>` : ""}
    <article class="letter" aria-labelledby="noteTitle">
      <h3 id="noteTitle" class="letter-label">A note for ${esc(parentWord())} <span class="muted">· ${esc(plan.language)}</span></h3>
      <p class="letter-text" id="parentMsg">${esc(plan.message_for_parent)}</p>
      <button type="button" class="btn btn-quiet btn-small" data-copy="parentMsg">Copy the note</button>
    </article>
    <div class="tabs" role="tablist" aria-label="Your week">
      ${WEEK_TABS.map(([k, l]) => `<button type="button" role="tab" id="tab-${k}" aria-controls="panel-${k}" aria-selected="${k === tab}" tabindex="${k === tab ? 0 : -1}" data-tab="${k}">${l}${k === "shop" ? ` <span class="count">${shopping.length}</span>` : ""}</button>`).join("")}
    </div>
    ${WEEK_TABS.map(([k]) => `<div class="tab-panel" role="tabpanel" id="panel-${k}" aria-labelledby="tab-${k}" tabindex="0" ${k === tab ? "" : "hidden"}>${panels[k]}</div>`).join("")}`;
  refreshButtons();
}

function selectTab(k, focus) {
  state.weekTab = k;
  document.querySelectorAll("#planOut [role=tab]").forEach((t) => {
    const on = t.dataset.tab === k;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    if (on && focus) t.focus();
  });
  document.querySelectorAll("#planOut [role=tabpanel]").forEach((p) => { p.hidden = p.id !== `panel-${k}`; });
}

async function makePlan(btn) {
  const out = $("planOut");
  const holder = document.createElement("p");
  holder.className = "working";
  out.prepend(holder);
  const stop = ticker(holder, `<span class="spinner" aria-hidden="true"></span><span>Planning 7 days and the shopping list<span class="dots"></span></span>`);
  const condition = state.condition;
  const version = state.cookbookVersion;
  try {
    const recipes = state.recipes.map((e) => baseFields(current(e)));
    const { plan } = await busy(btn, "Planning…", () => api("/api/plan", { recipes, condition, language: state.language }));
    stop();
    // Drop a late reply if the cookbook or health focus changed while Ultra was planning.
    if (state.condition !== condition || state.cookbookVersion !== version) {
      holder.remove();
      if (state.condition === condition) announce('Your dishes changed while planning. Tap "Plan our week" again.');
      return;
    }
    state.plan = plan; state.planStale = false; state.weekTab = "meals";
    renderPlan();
    $("s3").focus({ preventScroll: true });
    announce("Your week is ready, with a note for your parent and a shopping list.");
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
$("language").addEventListener("change", (e) => { state.language = e.target.value; renderNames(); updateMicHint(); });
$("parentName").addEventListener("input", (e) => {
  state.parentName = e.target.value.slice(0, 20);
  clearTimeout(state._nameTimer);
  state._nameTimer = setTimeout(() => { renderNames(); renderSummary(); if (state.plan) renderPlan(); }, 300);
});

document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => goToStep(Number(b.dataset.goto))));

$("families").addEventListener("click", (e) => {
  if (e.target.closest("[data-retry]")) { loadFamilies(); return; }
  const btn = e.target.closest("[data-family]");
  if (btn && !btn.hasAttribute("aria-busy")) loadFamily(btn.dataset.family, btn);
});

$("startOwn").addEventListener("click", () => {
  const hadDemo = Boolean(state.family);
  state.adaptRun += 1;
  state.started = true; state.own = true;
  if (hadDemo) {
    state.family = null; state.recipes = []; state.plan = null; state.planStale = false; state.parentName = ""; state.cookbookVersion += 1;
    $("adaptProgress").hidden = true;
    renderFamilies(); syncControls(); renderCookbook(); renderPlan();
  }
  $("startOwn").setAttribute("aria-pressed", "true");
  refreshButtons();
  $("about").open = true;
  $("addBox").open = true;
  scrollToEl($("stepDishes"));
  $("parentName").focus({ preventScroll: true });
  announce(hadDemo ? "Cleared the demo dishes. Tell us about them, then add your first recipe." : "Tell us about them, then add your first recipe.");
});

document.querySelectorAll(".stepper-btn").forEach((b) => b.addEventListener("click", () => {
  const input = $("servings");
  input.value = Math.min(20, Math.max(1, (Math.round(num(input.value)) || 4) + Number(b.dataset.step)));
}));

$("parse").addEventListener("click", (e) => parseRecipe(e.currentTarget));
$("recipeText").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("parse").click(); }
});

// Remember which cards are expanded so a re-render doesn't snap them shut.
$("cookbook").addEventListener("toggle", (e) => {
  const d = e.target;
  if (!d.matches || !d.matches("details[data-more]")) return;
  const entry = findEntry(d.dataset.more);
  if (entry) entry.open = d.open;
}, true);

$("cookbook").addEventListener("click", (e) => {
  const a = e.target.closest("[data-adapt]");
  if (a) { adaptOne(a.dataset.adapt); return; }
  const u = e.target.closest("[data-undo]");
  if (u) {
    const entry = findEntry(u.dataset.undo);
    if (entry) {
      entry.adapted = null; entry.status = "idle"; entry.open = false;
      markCookbookChanged();
      renderCard(entry.id); renderPlanStale();
      document.querySelector(`[data-card="${CSS.escape(entry.id)}"] [data-adapt]`)?.focus({ preventScroll: true });
      announce(`${entry.base.name}: showing the original recipe.`);
    }
    return;
  }
  const rm = e.target.closest("[data-remove]");
  if (rm) {
    const entry = findEntry(rm.dataset.remove);
    state.recipes = state.recipes.filter((x) => x.id !== rm.dataset.remove);
    markCookbookChanged();
    renderCookbook(); renderPlanStale();
    $("s2").focus({ preventScroll: true });
    if (entry) announce(`Removed ${entry.base.name}.`);
  }
});

$("adaptAll").addEventListener("click", (e) => adaptAll(e.currentTarget));
$("plan").addEventListener("click", (e) => makePlan(e.currentTarget));

$("planOut").addEventListener("click", async (e) => {
  const t = e.target.closest("[data-tab]");
  if (t) { selectTab(t.dataset.tab, false); return; }
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  let text = "";
  if (b.dataset.copy === "parentMsg") text = state.plan?.message_for_parent || "";
  else text = (state.plan?.shopping_list || []).map((s) => `${s.item}: ${grams(s.grams)}`).join("\n");
  const ok = await copyText(text);
  toast(ok ? "Copied. Paste it anywhere." : "Couldn't copy. Please select the text and copy it.");
});

$("planOut").addEventListener("keydown", (e) => {
  const t = e.target.closest("[role=tab]");
  if (!t) return;
  const keys = WEEK_TABS.map(([k]) => k);
  let i = keys.indexOf(t.dataset.tab);
  if (e.key === "ArrowRight") i = (i + 1) % keys.length;
  else if (e.key === "ArrowLeft") i = (i - 1 + keys.length) % keys.length;
  else if (e.key === "Home") i = 0;
  else if (e.key === "End") i = keys.length - 1;
  else return;
  e.preventDefault();
  selectTab(keys[i], true);
});

// ---------- start ----------
async function loadFamilies() {
  const box = $("families");
  box.innerHTML = Array.from({ length: 4 }, () => `<div class="family skeleton" aria-hidden="true"></div>`).join("");
  try {
    state.families = await api("/api/demo");
  } catch { state.families = []; }
  state.familiesLoaded = true;
  renderFamilies();
}

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
  await loadFamilies();
}

init();
