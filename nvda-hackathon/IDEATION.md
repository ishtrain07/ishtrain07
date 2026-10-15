# NVDA Hackathon: Final Idea (v4, SME focus)

**Event:** Nebius x NVIDIA Global AI Hackathon (Devpost) · **Track:** Best Apps & Agents
**Deadline:** Oct 30, 2026, 10:00 AM PT (from search results quoting Devpost; verify on the site) · **Internal freeze:** Oct 28
**Team:** Ish (ML/data, backend, agent pipeline) + co-founder (idea, UX/UI, story, video)

## 1. Constraints we're optimizing for
1. **Helps SMEs** (small and medium businesses).
2. **Easy to implement:** no OCR, no telephony, no hardware, no private data access.
3. **Design is 25% of the score**, and the co-founder is a UI person, so pick something whose value *shows* in an interface.
4. Explainable to a non-technical judge in one sentence.
5. Uses the stack the way the brief asks: Nemotron **Nano/Super for fast calls, Ultra for heavy reasoning**, **Serverless Endpoints/Jobs**, plus **Tavily** (bonus prize).

## 2. SME sweep (by business function, not by document type)

| Function | Idea | One sentence | Easy? | Verdict |
|---|---|---|---|---|
| **Getting found** | **Mentioned** | Customers now ask AI "who's the best X near me?" It checks whether AI recommends you, shows who it recommends instead and why, and writes the fixes. | ✅ API calls only | 🏆 **PICK** |
| Getting found | Google Business Profile optimizer | Improves your Google listing. | ✅ | ❌ classic SEO, commodity |
| Sales | Missed-call → text-back → booking for trades | Texts back missed callers and books the job. | ❌ telephony | ❌ |
| Sales | Voice-to-quote for tradespeople | Turns a spoken job description into a quote. | ✅ | ⚠️ useful but small |
| Sales | Tender Scout: public contracts matched + drafted | Finds public tenders that fit you and drafts the response. | ⚠️ messy per-country data | ⚠️ |
| Customer | Review auto-responder | Writes replies to reviews. | ✅ | ❌ cliché |
| Customer | Mystery-shopper agent tests your own inbox/chat | Contacts your business as a customer and scores the response. | ⚠️ | ❌ niche |
| Operations | Shop Brain: owner talks, it becomes SOPs and a training app | Turns what's in the owner's head into a training manual. | ⚠️ speech + UI heavy | 🥈 runner-up |
| Operations | Reorder / dead-stock agent from POS export | Tells a small retailer what to reorder and what to discount. | ✅ | ❌ low stand-out |
| Compliance | Licence and filing deadline calendar | Lists every filing and renewal deadline for your business. | ⚠️ accuracy is risky | ❌ |
| Compliance | Kitchen health-inspection pre-check from photos | Flags likely violations before the inspector does. | ⚠️ vision reliability | ❌ |
| Finance | Invoice Watch (supplier overcharges) | Catches suppliers overcharging. | ⚠️ OCR | ❌ less UI-driven, OCR risk |
| Finance | Cash-flow forecaster from bank CSV | Forecasts cash from bank exports. | ✅ | ❌ commodity |
| Procurement | Supplier quote comparator | Puts competing quotes side by side. | ⚠️ | ❌ document pattern again |
| Hiring | Job-post writer and screener | Writes job posts and screens applicants. | ✅ | ❌ cliché |

### Final scoring (1-10, /60)

| Idea | Easy to build | SME pain | Explain | Stand-out | Design showcase | Stack + Tavily fit | **Total** |
|---|---|---|---|---|---|---|---|
| **Mentioned** | **9** | 8 | **10** | **9** | **9** | **10** | **55** |
| Shop Brain | 6 | 8 | 9 | 7 | 9 | 7 | 46 |
| Invoice Watch | 6 | 9 | 9 | 8 | 6 | 7 | 45 |
| Tender Scout | 6 | 7 | 8 | 7 | 6 | 9 | 43 |
| Voice-to-quote | 8 | 7 | 9 | 5 | 7 | 6 | 42 |

## 3. ✅ COMMITTED: **Mentioned** (working name)

> **"Your customers stopped Googling. They ask AI. Does it mention you?"**

### The problem
Discovery is shifting from a list of 10 blue links to **one AI answer**: "best bakery in Leslieville", "emergency plumber near me open now", "affordable physio in Brampton that takes walk-ins". An AI answer names 3-5 businesses, and **if you're not one of them, you don't exist**.
- Big brands pay for enterprise "AI visibility" tools. A bakery, plumber or dental clinic has no idea whether AI recommends them, or why not.
- What AI answers draw on is often fixable: missing hours, no menu or prices online, no FAQ, thin reviews, no structured data, inconsistent name/address. SMEs just can't see it.

### What the owner does (2 minutes)
1. Enters **business name + city + category** (and their website, optional).
2. Watches a live scan: "Asking 25 customer questions the way your customers ask them…"
3. Gets a **Visibility Score**, a **competitor leaderboard**, the reasons behind it, and a list of **ready-to-paste fixes**.
4. Optionally gets a weekly re-check email: "You now appear in 9/25 answers, up from 3."

### What the agent does
| Step | Nebius / NVIDIA piece | Detail |
|---|---|---|
| 1. Generate realistic customer questions | **Nemotron Nano** | 25 queries across intents: "best", "cheap", "open now", "kid-friendly", "near [neighbourhood]", "vs [competitor]". |
| 2. Research the web like an AI assistant does | **Tavily** | Live search per query; collect the sources an AI answer would use. |
| 3. Simulate the AI answer | **Nemotron Super** | Answer each query from those sources the way an assistant would, naming 3-5 businesses. |
| 4. Score | Python | Mention rate, rank position, share of voice vs competitors, which queries you win or lose. |
| 5. Diagnose *why* | **Nemotron Ultra** | Compare your web footprint against the winners: "They list prices and hours, have an FAQ answering 'gluten-free?', and are on 4 directories you're missing." |
| 6. Write the fixes | **Nemotron Super** | Paste-ready FAQ copy, Google Business description, schema.org JSON-LD, a review-request message for customers, and the directory listings to claim. |
| 7. Weekly re-scan | **Nebius Serverless Jobs** | Background monitoring with a trend line. |
| App + demo URL | **Nebius Serverless Endpoints** | FastAPI backend + web UI. |

**The honest framing (an answer for judges):** we don't scrape ChatGPT. We run a *transparent, reproducible AI-search panel*: live web retrieval (Tavily) + an open model (Nemotron) answering the way assistants do. Because it's open and repeatable, a business can see exactly which sources drove each answer. Proprietary assistants can't show you that.

### Why this is the one
- **SME pain that's real and timely:** AI search is reshaping local discovery right now.
- **Easiest build of all candidates:** text in, text out, API calls, no OCR, phones, video or private data. A working core in ~4 days.
- **Built for a design-led team:** the scorecard, the competitor leaderboard and "here's what AI says about you" are inherently visual. The co-founder's work *is* the product.
- **Tavily is load-bearing,** so we're a strong contender for **Best Use of Tavily** on top of the main prizes.
- **Every Nemotron tier has a real job** (Nano = volume, Super = answers and fixes, Ultra = diagnosis), exactly as the Apps & Agents brief describes.
- **Demo moment:** type in a real local business → "AI mentions you in **3 of 25** answers. It recommends *these* 4 competitors instead, and here's why" → tap "Fix it" → paste-ready fixes.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| "It's just SEO" | It's an agent that *simulates the new channel, explains why, and writes the fixes*. SEO tools rank keywords; this measures whether AI recommends you. |
| Results vary run to run | Fixed seeds/temperature 0 for scoring, 25 queries for statistical stability, and confidence shown on the score. |
| Simulated answer ≠ ChatGPT's answer | State it openly. Position it as a transparent panel and show the sources behind every answer. |
| Tavily / Token Factory rate limits or cost | Cache per business, Nano for the bulk, Ultra called once per report. |
| Demo business looks bad on camera | Use a willing real business (a friend's café/shop), or one that's clearly public and well known, framed positively. |

## 4. Who does what

| Ish (pipeline + infra) | Co-founder (product + UI + story) |
|---|---|
| Token Factory setup, Nemotron Nano/Super/Ultra calls | Name, brand, landing page |
| Query generator, Tavily retrieval, answer simulator | Flow: input → live scan → score → leaderboard → fixes |
| Scoring + diagnosis + fix generation (JSON contracts for the UI) | Scorecard, competitor leaderboard, "what AI says about you" view, fix cards with copy buttons |
| FastAPI on Serverless Endpoints; weekly re-scan on Serverless Jobs | Recruit 2-3 real local businesses for the demo + a quote |
| README (setup, Nemotron/Token Factory/Nebius section), FEEDBACK.md | 3-min video script, Devpost description, thumbnail |

**Contract between us (agree on Day 1):** a single JSON report schema (`score`, `queries[]`, `competitors[]`, `reasons[]`, `fixes[]`). The co-founder builds the UI against mock JSON from Day 1, so the two of us never block each other.

## 5. Build plan

| Dates | Ish | Co-founder |
|---|---|---|
| Oct 16 | Builder Program credits (Token Factory + Tavily); first Nemotron call; draft JSON schema | Name + brand; wireframes; pick 3 demo businesses |
| Oct 17-19 | Query gen → Tavily → answer simulation → mention scoring (CLI) | UI on mock JSON: input + live scan + scorecard |
| Oct 20-22 | Ultra diagnosis + fix generation; caching. **End-to-end via CLI by Oct 22.** | Leaderboard + fix cards; landing page |
| Oct 23-24 | FastAPI + streaming progress; **deploy on Serverless Endpoints** | Wire UI to the real API |
| Oct 25-26 | Weekly re-scan on Serverless Jobs; harden; rate limits | Polish, mobile, empty/error states |
| Oct 27 | Run the 3 real businesses; fix rough edges | Collect quotes/reactions from those owners |
| Oct 28 | **Feature freeze.** README, LICENSE (MIT), FEEDBACK.md | Video script + storyboard |
| Oct 29 | Support video recording | Record/edit ≤3-min video → YouTube; Devpost text |
| **Oct 30, before 10 AM PT** | Submit together | |

### Submission checklist
- [ ] Track: Best Apps & Agents
- [ ] Description (what / why / how)
- [ ] Demo URL (Nebius Serverless Endpoint)
- [ ] Public YouTube video ≤3 min showing Token Factory + Nemotron (show the Nano/Super/Ultra trace)
- [ ] New public repo with an MIT LICENSE visible at the top
- [ ] README: setup, run, how Nemotron / Token Factory / Tavily / Serverless are used
- [ ] Feedback on Token Factory / NVIDIA models
- [ ] City selection if attending a Builders & Brews event

## 6. Last decisions (small)
1. Final name: *Mentioned* is a placeholder; the co-founder decides.
2. New public repo name (e.g. `mentioned-ai`), plus both of you added as collaborators.
3. Which 3 real local businesses do we demo with?

## Appendix: official rules
- Must run on **Nebius Token Factory or AI Cloud** and use **≥1 NVIDIA open model**.
- Required: working demo URL, public YouTube video ≤3 min showing Token Factory + Nemotron, public repo with an OSS license, README with Nemotron/Token Factory/Nebius usage, feedback, and a disclosure of pre-existing code.
- Judging (equal weight): Technological Implementation · Design · Potential Impact · Quality of Idea.
- Earlier rounds: v1 Receipts (no recurring use), v2 Invoice Watch (too narrow a pattern), v3 broad sweep (Curb Cut / Misconception Map). All dropped in favour of an SME focus.
