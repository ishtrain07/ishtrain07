# NVDA Hackathon: Ideation v2 (from scratch)

**Event:** Nebius x NVIDIA Global AI Hackathon (Devpost)
**Deadline:** Oct 30, 2026, 10:00 AM PT (from search results quoting Devpost; verify on the site)
**Status:** ideation only. No code until the idea is locked.

## 0. Why v1 (Receipts) was dropped

Receipts was clever but failed the "who uses this every week?" test. Checking a finfluencer claim is something people *should* do but almost never *would* do. Judges score **Potential Impact** and **Quality of Idea**, and a clever tool without a recurring pain loses both.

## 1. New filter: every idea must pass all five

1. **A real person, a real recurring pain.** The user can be named ("a restaurant owner", "a renter"), and the problem shows up weekly or monthly.
2. **Explainable in one sentence** to a non-technical judge.
3. **Money or time recovered is visible on screen** ("found $412").
4. **Niche, not cliché.** Not a chatbot, RAG-over-docs, tutor, meeting summarizer, or resume tool.
5. **Shippable solo in about 12 days** on Token Factory + Nemotron, with a hosted demo URL.

## 2. Official rules that shape the idea (from Devpost text)

- Must run on **Nebius Token Factory or AI Cloud** and use **≥1 NVIDIA open model** (Nemotron).
- **Best Apps & Agents** track explicitly wants: Nemotron 3 **Ultra** for heavy reasoning, **Nano/Super** for fast calls, and optionally **Serverless Endpoints** (app) and **Serverless Jobs** (background work).
- **Personal AI** track expects NemoClaw / OpenShell / Hermes Agent tooling. These are new to us, so that track is riskier.
- Required: working **demo URL**, public **YouTube video ≤3 min** showing Token Factory + Nemotron, **public repo with OSS license**, README with Nemotron/Token Factory/Nebius usage, **feedback**, and a disclosure of any pre-existing code.
- Judging (equal weight): Technological Implementation · Design · Potential Impact · Quality of Idea.

## 3. Longlist (fresh)

| # | Idea | Who | One sentence | Verdict |
|---|---|---|---|---|
| A | **Invoice Watch** | Independent restaurant / café owner | Snap your supplier invoices; it catches price creep, short shipments and billing errors, and writes the credit request. | ✅ Top 5 |
| B | **Deposit Defender** | Renters | Walk-through photos at move-in and move-out; it builds the evidence pack and the letter to get your deposit back. | ✅ Top 5 |
| C | **Sheet Lint** | Anyone running a business on spreadsheets | A linter for spreadsheets: it writes and runs checks that find hard-coded overrides, broken ranges and double-counts. | ✅ Top 5 |
| D | **Money Left Behind** | Busy households | Reads your receipts and finds return windows, price drops and warranty claims you're about to miss. | ✅ Top 5 |
| E | **Grant Scout** | 1-5 person nonprofits | Finds grants you actually qualify for this month and pre-drafts the application. | ✅ Top 5 |
| F | Finance claim auditor (old v1 pick, Receipts) | Retail investors | Turns finance claims into backtests. | ❌ low recurring use |
| G | Job-site safety spotter from photos | Small contractors | Flags safety violations in site photos. | ❌ liability, hard to verify |
| H | Parking-ticket contester | Drivers | Drafts parking-ticket appeals. | ❌ DoNotPay did it, and it went badly |
| I | Insurance denial appeals (old #2, Denied) | Patients | Drafts appeals for denied health-insurance claims. | ❌ already exists as open source; private data |
| J | Freelancer late-invoice chaser | Freelancers | Sends escalating reminders for unpaid invoices. | ❌ useful but low tech showcase |
| K | School-email digest for parents | Parents | Digests school emails for parents. | ❌ Personal-AI cliché |
| L | Rec-league stat keeper from phone video | Amateur sports | Keeps stats from phone video. | ❌ video pipeline too hard in 12 days |

## 4. Top 5 scored (1-10 each, /60)

**Feasibility** = shippable solo by Oct 28 · **Real pain** = how often and how badly it hurts · **Explain** = one-sentence clarity · **Stand-out** = memorable among ~hundreds · **Tech** = makes Nemotron tiers, Token Factory and Serverless do real work · **Demo** = lands in 3 min

| Idea | Feasibility | Real pain | Explain | Stand-out | Tech | Demo | **Total** |
|---|---|---|---|---|---|---|---|
| **A. Invoice Watch** | 8 | **9** | **9** | 8 | 8 | **9** | **51** |
| B. Deposit Defender | 7 | 8 | **10** | 8 | 7 | 9 | **49** |
| C. Sheet Lint | 8 | 7 | 9 | 7 | **9** | 7 | **47** |
| D. Money Left Behind | 6 | 7 | 9 | 6 | 6 | 7 | **41** |
| E. Grant Scout | 8 | 7 | 8 | 5 | 6 | 6 | **40** |
| *(old) Receipts* | 8 | 4 | 6 | 8 | 9 | 8 | *43* |

**B. Deposit Defender (49).** Easiest to explain of all ("get your deposit back"). The risk is that the vision model has to spot real damage differences between two photo sets reliably. If it misses a scratch on camera, the demo dies. It also gets used once per move, not weekly.

**C. Sheet Lint (47).** Best tech fit (it's literally "agents that write, run and test code"), and spreadsheet errors are a well-documented, expensive problem. But "your cell B14 is hard-coded" is less emotional on screen, and the Coding track is the most crowded.

**D. Money Left Behind (41).** A clear pain, but it needs email/receipt access and retailer policy data that varies by store. Too much plumbing for the time we have.

**E. Grant Scout (40).** Practical, but it looks like a search-and-summarize app. Low stand-out.

## 5. The pick: **Invoice Watch** (working name)

> **"Your suppliers raise prices a little at a time. Snap the invoice. We catch it and get your money back."**

### The use case, plainly
An independent restaurant owner receives 10-30 supplier invoices a week (produce, meat, dairy, dry goods). Prices change constantly, and errors happen: a case of tomatoes billed at a new price nobody agreed to, 9 cases delivered but 10 billed, a "fuel surcharge" that wasn't there last month, a contracted price ignored. Owners are too busy to compare line by line, and independent restaurants run on thin margins, so these small leaks matter. **Nobody checks, so nobody gets the money back.**

### What the user does (30 seconds a day)
1. Takes a photo of each invoice (or forwards the PDF email).
2. Gets a weekly "leak report" plus instant alerts on big ones.
3. Taps **"Send credit request"** to send a pre-written, polite, evidence-backed email to the supplier rep.

### What the agent does
| Step | Model / service | Job |
|---|---|---|
| Read invoice photo/PDF → line items (item, pack size, qty, unit price, fees) | **Nemotron Nano VL/Omni** (multimodal) | Fast extraction, many calls |
| Normalize items across suppliers and wording ("TOM ROMA 25#" = "Roma tomatoes 25 lb") | **Nemotron Super** | Fuzzy matching against the restaurant's item catalog |
| Detect leaks: price creep vs. last N invoices or the agreed price list, qty mismatches, new fees, math errors, duplicate invoices | Plain Python rules + **Super** for edge cases | Deterministic checks keep it trustworthy |
| Explain + prioritize ("$412 this month, 70% from 3 items") and draft the credit request | **Nemotron Ultra** | One heavy reasoning call per report |
| Nightly reconciliation across all invoices | **Nebius Serverless Jobs** | Background processing |
| Web app + public demo URL | **Nebius Serverless Endpoints** | Hosting |
| *(Optional)* "Is this price above market?" check vs. public wholesale prices | Tavily | Extra context, not core |

### Why this one
- **Real, recurring, painful, and measurable**: the output is a dollar figure.
- **One-sentence explainable** to any judge, technical or not.
- **Niche and not cliché.** Most hackathon AI is for knowledge workers; this is for a kitchen.
- **Uses the stack the way the track text asks**: Nano for volume, Super for matching, Ultra for reasoning, Serverless Jobs + Endpoints. That's straight from the Apps & Agents brief.
- **Clear demo arc**: drop in 4 weeks of invoices → a line chart of creeping prices → "$412 found" → one-tap credit email.
- **Extends naturally** to any small business with recurring suppliers (salons, clinics, contractors), which makes a strong "potential impact" slide.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Invoice photos are messy | Demo with clean PDFs + 2 real phone photos, and show a correction UI for low-confidence lines. |
| No real invoices to test on | Generate a realistic synthetic dataset (3 suppliers × 6 weeks, with planted errors). **Best case: ask one local restaurant or café for 3-4 real invoices** (with permission, redacted). That one real data point makes the pitch much stronger. |
| False alarms annoy users | Thresholds + "why flagged" evidence on every alert. Nothing is sent without the owner's tap. |
| Item matching errors | A catalog built on first upload, the user confirms matches once, and the system remembers them. |

## 6. Build plan (Oct 16-30)

| Dates | Milestone |
|---|---|
| Oct 16 | Lock the idea. Nebius Builder Program sign-up (credits). First Nemotron call on Token Factory. Confirm which Nemotron VL/Omni model is available for image input. |
| Oct 17-18 | Synthetic invoice dataset with planted errors; (ideally) 3-4 real invoices. |
| Oct 19-21 | Extraction (Nano VL) → item normalization (Super) → SQLite price history. |
| Oct 22-23 | Leak detectors + Ultra report + credit-request drafting. **End-to-end works by Oct 23.** |
| Oct 24-25 | Deploy on Serverless Endpoints; nightly job on Serverless Jobs. **Public URL live.** |
| Oct 26-27 | UI polish: upload, price-creep chart, leak list, one-tap email. |
| Oct 28 | Feature freeze. README (setup, Nemotron/Token Factory/Nebius section), LICENSE, `FEEDBACK.md`. |
| Oct 29 | ≤3-min YouTube video + Devpost text. |
| **Oct 30, before 10 AM PT** | Submit. |

### Submission checklist
- [ ] Track: Best Apps & Agents
- [ ] Description (what / why / how)
- [ ] Demo URL (Serverless Endpoint)
- [ ] Public YouTube video ≤3 min showing Token Factory + Nemotron
- [ ] New public repo with an OSS LICENSE visible at the top (not this profile repo)
- [ ] README with setup + Nemotron / Token Factory / Nebius usage
- [ ] Feedback on Token Factory / NVIDIA models
- [ ] City selection if attending a Builders & Brews event

## 7. Decisions needed from you
1. Invoice Watch, or the runner-up **Deposit Defender**?
2. Do you know a restaurant, café or food truck that would share 3-4 invoices?
3. Solo or team?
4. OK to create a new public repo for the submission?
