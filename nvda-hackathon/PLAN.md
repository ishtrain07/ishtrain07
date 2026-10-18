# Mentioned: Build Plan (v1, Oct 18, 2026)

Source of truth for the idea: `IDEATION.md`. This file replaces its section 5 build plan, which started Oct 16 and is out of date.

**Status (Sun Oct 18):** 11 working days to feature freeze (Wed Oct 28), 12 to submission (Fri Oct 30, 10:00 AM PT). **Slightly behind**: the Oct 16-17 setup (credits, first Nemotron call, schema) has not happened. We can recover today if setup and the JSON contract are done before tonight.

## 0. Assumptions (stated, not asked)
- Both founders are part-time: about 3-4 h on weekdays and 6-8 h on weekend days. That gives **~50 h each to freeze and ~100 person-hours in total**. Remaining weekends: Oct 18, Oct 24-25.
- Neither of us has used Token Factory yet. Builder Program credits (Token Factory + Tavily) **may not be approved**, so we start on pay-as-you-go and free tiers today and don't wait.
- Our strength is product and design, so we use the simplest proven tools: one FastAPI app that serves the API **and** the static frontend, in one container behind one URL. No database (JSON files on disk), no auth, no queue.
- The rules require the project to run on **Token Factory or AI Cloud**. All inference goes through Token Factory, so hosting can fall back without breaking the rules.

## 1. Web check (Oct 18)
| Question | Finding | Confidence / action |
|---|---|---|
| Token Factory API | OpenAI-compatible. Base URL `https://api.tokenfactory.us-central1.nebius.com/v1/`, key in `NEBIUS_API_KEY`, standard `openai` Python client. ([Nebius Nemotron page](https://nebius.com/services/token-factory/nemotron), [docs](https://docs.tokenfactory.nebius.com/api-reference/examples/overview)) | High |
| Nemotron Nano | Nemotron 3 Nano 30B (A3B) is listed on Token Factory. ([Nebius](https://nebius.com/services/token-factory/nemotron), [TypingMind catalog](https://custom.typingmind.com/tools/estimate-llm-usage-costs/nebius/nvidia-nemotron-3-nano-30b-a3b)) | High. Confirm the exact ID in the console |
| Nemotron Super | `nvidia/nemotron-3-super-120b-a12b`. 12B active parameters, up to 1M context. ([Nebius blog](https://nebius.com/blog/posts/nemotron3-super-now-available)) | High |
| Nemotron Ultra | Nemotron 3 Ultra 550B (A55B), released Jun 4, 2026. Third-party catalogs list it on Nebius as `nvidia/Nemotron-3-Ultra-550b-a55b` at about $1 in / $3 out per 1M tokens. The catalogs disagree on ID casing. ([TypingMind](https://custom.typingmind.com/tools/estimate-llm-usage-costs/nebius/nemotron-3-ultra-550b-a55b), [Requesty](https://www.requesty.ai/models-new/nebius/nvidia-nemotron-3-ultra-550b-a55b), [Eden AI](https://www.edenai.co/models/nemotron-3-ultra-550b-a55b)) | **Medium**: not confirmed on Nebius's own docs. Call it today. Fallback: Super does the diagnosis |
| Serverless Endpoints for FastAPI | Endpoints run any container image (public or private registry). An HTTP port gets a managed `https://` URL, and auth is `none` or `token`. ([quickstart](https://docs.nebius.com/serverless/quickstart/endpoints.md), [manage](https://docs.nebius.com/serverless/endpoints/manage), [CLI create](https://docs.nebius.com/cli/reference/ai/endpoint/create), [launch blog](https://nebius.com/blog/posts/introducing-serverless)) | **Medium**: it is GPU-oriented, and I found no clear CPU-only preset, so cost and idle billing are unknown. Spike it Oct 19-20 |
| Serverless Jobs | Container-based in the same way, so it can run `python rescan.py` ([launch blog](https://nebius.com/blog/posts/introducing-serverless)). I did not confirm that cron scheduling exists. | Stretch only |

**Hosting decision rule:** a hello-world FastAPI container on Serverless Endpoints by **Tue Oct 20, end of day**.
- If it works and the cost is acceptable, keep it.
- Otherwise use **Fallback A**: a small CPU VM on Nebius AI Cloud running `docker run` with Caddy for HTTPS.
- **Fallback B** (last resort): the same container on any simple host (Render/Fly/Railway), with all inference still on Token Factory.

## 2. Scope check: what in IDEATION.md is too big
| IDEATION item | Problem | MVP decision |
|---|---|---|
| 25 queries per scan | 25 Tavily calls plus 25 Super answers takes minutes per scan and burns the Tavily free tier | **10 queries**, run in parallel (thread pool of 5). Score shown as "mentioned in X of 10" |
| Weekly re-scan on Serverless Jobs + email + trend line | Adds scheduling, storage, email, a 2nd deploy target and a new UI view. Not part of the video's core story | **Cut from MVP.** Stretch: one Serverless Job run of `rescan.py` writing a 2nd report, shown as "before → after" |
| 5 fix types (FAQ, GBP description, JSON-LD, review request, directory listings) | Directory listings need real directory data, which is an accuracy risk | **3 fixes: FAQ copy, Google Business description, schema.org JSON-LD.** Review request is the first stretch item |
| Ultra compares "your web footprint vs the winners" | An open-ended crawl | Footprint = Tavily results for you + top 3 competitors (already fetched) + optional `tavily extract` of your homepage. **One Ultra call per report** |
| Live streaming scan | SSE/websockets are fiddly on serverless | Background task + **polling** `GET /api/scan/{id}` every 1.5 s, returning step progress. The UI animates the steps |
| Score confidence, share-of-voice math | Nice but not demo-critical | Keep mention rate, average rank and the competitor leaderboard. Confidence = "X of 10" |
| 3 real businesses + owner quotes | Recruiting takes time we don't have | **1 willing real business** (consent + quote) + **2 well-known public ones**. Cache all 3 as golden reports |
| Mobile polish | Judges watch the video on desktop | Responsive enough not to break. No dedicated mobile pass |

**Trimmed MVP (what the video shows):** enter name + city + category (+ website) → animated scan (Nano → Tavily → Super) → **Visibility Score** + **competitor leaderboard** → **"What AI says"** per query, with the sources → **"Why" (Ultra)** → **3 fix cards with copy buttons** → **model trace panel** showing which Nemotron tier did each step, with tokens and latency. It runs on a public URL, and golden reports load instantly.

## 3. JSON report contract (freeze today, v0)
Ish commits `mock/report.json` today. The co-founder builds only against this file. Any change needs both of us to agree.
```json
{
  "id": "scan_abc123", "status": "running|done|error",
  "progress": [{"step": "queries|search|answers|score|diagnose|fixes", "state": "pending|running|done", "detail": "6/10 answers"}],
  "business": {"name": "", "city": "", "category": "", "website": ""},
  "score": {"mentioned": 3, "total": 10, "avg_rank": 2.7, "label": "Low|Medium|High"},
  "queries": [{"q": "best bakery in Leslieville", "intent": "best", "mentioned": true, "rank": 2,
               "answer": "...", "businesses": ["A", "B"], "sources": [{"title": "", "url": ""}]}],
  "competitors": [{"name": "", "mentions": 7, "avg_rank": 1.4}],
  "reasons": [{"title": "Competitors list prices and hours", "detail": "", "evidence_urls": [""]}],
  "fixes": [{"type": "faq|gbp_description|jsonld", "title": "", "content": "", "why": ""}],
  "trace": [{"step": "diagnose", "model": "nvidia/Nemotron-3-Ultra-...", "tokens_in": 0, "tokens_out": 0, "ms": 0}]
}
```
API: `POST /api/scan` → `{id}`; `GET /api/scan/{id}` → report (partial while running); `GET /api/demo/{slug}` → cached golden report. Static UI is served at `/`.

## 4. Milestones
| Date | Deliverable | Owner |
|---|---|---|
| **Sun Oct 18** | Repo + MIT LICENSE; Token Factory + Tavily keys; all 3 Nemotron models answer a test call; contract v0 + `mock/report.json`; name + wireframes | Ish / Co |
| Mon Oct 19 | CLI: Nano queries → Tavily → Super answers (1 business); hosting spike started | Ish |
| **Tue Oct 20** | Mention extraction + scoring; **hosting decision made** | Ish |
| Wed Oct 21 | Ultra diagnosis + 3 fixes. **CLI end to end writes a contract-valid report** | Ish |
| Wed Oct 21 | UI on mock data: input → scan steps → scorecard + leaderboard | Co |
| Thu Oct 22 | FastAPI (scan job, polling, cache, demo endpoint), Dockerfile, deployed | Ish |
| Fri Oct 23 | UI: "What AI says", Why, fix cards, trace panel (mock) | Co |
| **Sat Oct 24** | **Public URL, real end to end.** UI wired to real API. 3 golden reports cached | Both |
| Sun Oct 25 | Prompt/quality pass, error/empty states, rate limit; video script v1 | Both |
| Mon Oct 26 | **Buffer.** Stretch only if everything above is green | Both |
| Tue Oct 27 | README, FEEDBACK.md, disclosure of pre-existing code; video storyboard + rough screen capture | Ish / Co |
| **Wed Oct 28** | **Feature freeze.** Full submission dry run: every checklist item drafted | Both |
| Thu Oct 29 | Record + edit video (≤3 min), upload to YouTube (public), Devpost text final. **Target: submit Thu night** | Co (Ish supports) |
| Fri Oct 30 | Hard backstop: submitted by **8:00 AM PT** (2 h buffer) | Both |

## 5. Demo-critical path
`T1 keys` → `T2 model smoke test` → `T4 query gen` → `T5 Tavily` → `T6 answers` → `T7 scoring` → `T8 diagnose` → `T9 fixes` → `T10 API` → `T12 deploy` → `T15 wire UI` → `T16 golden reports` → `T20 video`.
UI tasks run in parallel on mock data and join at T15. Everything not on this path is a stretch item.

## 6. Task list (each ≤ half a day)
| ID | Task | Owner | Est | Deps | Done when |
|---|---|---|---|---|---|
| T0 | Public repo `mentioned-ai`, MIT LICENSE, `.env.example`, `.gitignore` (keys) | Ish | 0.5 h | - | LICENSE badge visible on GitHub; both are collaborators |
| T1 | Token Factory account (pay-as-you-go card, apply for credits), Tavily key | Ish | 1 h | - | Keys in `.env`; credit application sent |
| T2 | Smoke test Nano/Super/Ultra; record exact model IDs, latency, cost | Ish | 1 h | T1 | `scripts/smoke.py` prints 3 replies; IDs in `config.py` |
| T3 | Contract v0 + `mock/report.json` (realistic, 10 queries) | Ish | 1.5 h | - | Co-founder confirms the UI can render everything from it |
| T4 | Nano query generator (10 queries, mixed intents, JSON out) | Ish | 2 h | T2 | Gives 10 sensible queries for 3 test businesses |
| T5 | Tavily search per query, parallel, disk cache by query hash | Ish | 2 h | T1 | 2nd run makes 0 Tavily calls |
| T6 | Super answers from sources (temp 0, structured JSON: answer + named businesses) | Ish | 3 h | T4,T5 | Every answer names 3-5 businesses and cites URLs |
| T7 | Mention matching (rapidfuzz on names) + score + leaderboard | Ish | 2 h | T6 | Hand-check on 1 business: no false mentions |
| T8 | Ultra diagnosis (1 call): reasons + evidence URLs | Ish | 3 h | T7 | 3-5 specific reasons, no generic SEO filler |
| T9 | Super fixes: FAQ, GBP description, JSON-LD | Ish | 2 h | T8 | JSON-LD validates; copy is paste-ready |
| T10 | FastAPI: `POST/GET /api/scan`, background task, progress, `/api/demo/{slug}`, static serving, trace | Ish | 3 h | T9 | `curl` flow works locally |
| T11 | Hosting spike: hello-world container on Serverless Endpoint | Ish | 2 h | T0 | Public https URL returns 200, or fall back to the VM (decide by Oct 20) |
| T12 | Deploy the real app; global daily scan cap + per-IP limit | Ish | 3 h | T10,T11 | Stranger's browser runs a live scan on the public URL |
| U1 | Final name, logo, colour/type tokens | Co | 2 h | - | One-page brand sheet |
| U2 | Wireframes: input → scan → report (score, leaderboard, what AI says, why, fixes, trace) | Co | 3 h | - | Ish signs off that data exists for every element |
| U3 | Pick the demo businesses; get consent + quote from 1 real owner | Co | 2 h | - | Names + websites sent to Ish by Oct 20 |
| U4 | Build input + animated scan + scorecard + leaderboard (mock JSON) | Co | 2 × 0.5 d | T3,U2 | Renders `mock/report.json` |
| U5 | Build "What AI says" (sources), Why, fix cards with copy, trace panel | Co | 2 × 0.5 d | U4 | Same |
| T15 | Wire UI to the real API + polling; error/empty states | Both | 3 h | T12,U5 | Live scan works on the public URL |
| T16 | Run + cache 3 golden reports; tune prompts on them | Ish | 3 h | T15 | All 3 look credible on camera |
| T17 | README (setup, architecture, how Nemotron tiers / Token Factory / Tavily / Nebius are used) | Ish | 2 h | T12 | A fresh clone runs following the README |
| T18 | FEEDBACK.md (Token Factory, Nemotron, Serverless: real notes kept from day 1) | Ish | 1 h | - | Specific, honest, 1 page |
| T19 | Video script + storyboard (≤3 min; show Token Factory console + trace panel) | Co | 3 h | U5 | Timed read-through ≤2:45 |
| T20 | Record, edit, upload public YouTube | Co | 0.5 d | T16,T19 | Public link plays logged out |
| T21 | Devpost text, thumbnail, track = Best Apps & Agents, submit | Co | 3 h | T20 | Submitted; confirmation email received |

## 7. Today and tomorrow
**Ish, Sun Oct 18 (~7 h):** T0, T1, T2, T3 (send mock to the co-founder by ~2 PM), start T4. Start the FEEDBACK.md notes file.
**Ish, Mon Oct 19 (~3.5 h):** finish T4, then T5, then start T11 (container spike) in parallel.
**Co-founder, Sun Oct 18 (~7 h):** U1, U2, then contact demo businesses (U3). Review `mock/report.json` when it lands and flag missing fields today.
**Co-founder, Mon Oct 19 (~3.5 h):** U4 part 1 (input + scan animation). Follow up on U3.

## 8. Cut list (drop in this order if we slip)
1. Weekly re-scan / Serverless Job / email / trend line (already out of the MVP; stretch only)
2. Review-request fix (stretch), then the JSON-LD fix (keep FAQ + GBP)
3. Homepage extract in the diagnosis (use Tavily snippets only)
4. Trace panel as a UI component → replace it with a terminal/log shot in the video
5. Live scans for arbitrary businesses on the public URL → demo URL serves golden reports + live scan behind a "try your own" button with a low cap
6. Ultra → Super for the diagnosis (only if Ultra is unavailable or too slow; say so in the README)
7. Serverless Endpoint → AI Cloud VM → simple host (Section 1 rule)

**Never cut:** public URL, the 3 Nemotron-backed steps, the Tavily sources, fix cards, the video, the README/LICENSE/feedback.

**Stretch (only after Sat Oct 24 is green, and only on Oct 26-27):** review-request fix; a one-off Serverless Job re-scan shown as "before → after"; a shareable report link.

## 9. Top risks
| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Credits not approved / billing friction | Med / High | Pay-as-you-go today. Cost per scan is cents (10 Super calls + 1 Ultra). Cache everything. Set a spend alert |
| Ultra not callable, or slow (550B) | Med / Med | Smoke test today. One call per report, run async. Fall back to Super via config flag |
| Serverless Endpoints won't fit a CPU web app (GPU-only, cost, preview quirks) | Med / High | Spike by Oct 20; VM fallback; public URL by Oct 24 at the latest |
| Tavily free-tier limit | Med / Med | 10 queries/scan, disk cache, daily scan cap, golden reports for the demo |
| Scan too slow for the demo (>90 s) | Med / Med | Parallel calls, fewer queries, animated progress, cached golden reports for recording |
| Mention matching is wrong (false or missed mentions) | Med / High (credibility) | Structured JSON business lists from Super + fuzzy match + hand check on golden reports |
| Demo business looks bad / no consent | Low / Med | Consenting owner + well-known public names, framed positively |
| Part-time hours slip | High / High | Half-day tasks, Oct 26 buffer, cut list, freeze Oct 28, submit Oct 29 night |
| Keys leaked in the public repo | Low / High | `.env` gitignored from T0; secrets only in the host's env vars |
| Submission details (pre-existing code disclosure, feedback field, deadline) | Low / High | Re-read the Devpost rules at the Oct 28 dry run; confirm the deadline on Devpost |

## 10. Submission checklist (owner)
- [ ] Track: Best Apps & Agents (Co)
- [ ] Working demo URL (Ish)
- [ ] Public YouTube ≤3 min showing Token Factory + Nemotron Nano/Super/Ultra (Co)
- [ ] Public repo, MIT LICENSE visible at the top (Ish)
- [ ] README: setup, run, how Nemotron / Token Factory / Tavily / Nebius are used (Ish)
- [ ] Feedback on Nebius/NVIDIA tools (Ish)
- [ ] Pre-existing code disclosure (Ish)
- [ ] Devpost description + thumbnail (Co)
