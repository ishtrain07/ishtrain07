# NVDA Hackathon: Ideation (no code yet)

**Event:** Nebius x NVIDIA Global AI Hackathon (Devpost)
**Status:** ideation only. Nothing gets built until we lock the idea.

## 1. What the rules force on us

| Constraint | What it means for the idea |
|---|---|
| **Deadline: Oct 30, 2026, 10:00 AM PT** (not the 31st) | About 14 working days from Oct 15. Plan to finish on **Oct 28** and keep 2 days for the video and buffer. |
| Must run on **Nebius Token Factory or Nebius AI Cloud** | Inference goes through Token Factory's OpenAI-compatible API. Very little infra work. |
| Must use **at least one NVIDIA open model** | Nemotron 3 (Nano 30B / Super 120B / Ultra 550B / Nano Omni). Use Super as the reasoning brain and Nano for cheap, fast steps. |
| Public repo, open-source license, demo video of 3 min or less | The demo has to land in 3 minutes. Choose an idea that **shows** well, not one that needs explaining. |
| Tracks: Coding & Agentic Eng · Best Apps & Agents · Personal AI · Physical AI | Physical AI needs hardware and sim, so skip it with 15 days. The other three are open. |
| Judging: **Tech implementation · Design · Potential impact · Quality of idea** (equal weight) | Each counts 25%. A clever backend with a bad UI loses, and a pretty wrapper loses too. |
| Bonus: **$3k Best Use of Tavily** | Live web search is basically a free second prize ticket if it is load-bearing in the idea. |

> Note: devpost.com is blocked from this sandbox, so these details come from search results that quote the Devpost page and from secondary listings. **Check the deadline and rules on Devpost yourself.** The "Token Factory Sandboxes" mentioned for the coding track could not be confirmed, so the plan below has a fallback.

## 2. The longlist (12 ideas, cliché filter applied)

Cut immediately for being cliché: "chat with your PDFs", generic RAG bots, meeting summarizers, AI tutors, "travel planner agent", resume/job agents.

| # | Idea | Track | One-line pitch | Kept? |
|---|---|---|---|---|
| 1 | **Receipts**: finance claim → executable backtest | Coding/Agentic + Apps | Paste any "this strategy returns 40%/yr" post. An agent turns it into code, runs it on real data, and returns a verdict with the receipts. | ✅ Top 5 |
| 2 | **Denied**: health-insurance denial appeal agent | Personal AI | Upload a denial letter. It finds the policy clause, the clinical evidence and the appeal deadline, and drafts the appeal. | ✅ Top 5 |
| 3 | **Bill Autopsy**: hospital bill auditor | Personal AI | Itemized bill → CPT codes → flags duplicates/upcoding against price-transparency data → drafts a dispute. | ✅ Top 5 |
| 4 | **Repro**: issue-to-failing-test agent | Coding | Takes a GitHub issue, reproduces it in a sandbox, and opens a PR containing only a *failing test*. | ✅ Top 5 |
| 5 | **Council Watch**: civic agenda radar | Apps & Agents | Watches your city council agendas and minutes and alerts you in plain language when something affects *your* street, rent or school. | ✅ Top 5 |
| 6 | Paper-to-reproduction (reproduce an ML paper's claim) | Coding | Great idea, but a full run takes GPU-days. Too slow to demo. | ❌ |
| 7 | Sports film-room scout (Nemotron Omni on game video) | Apps | Fits your sports interest, but video plus labels is a data swamp in 15 days. | ❌ |
| 8 | Pill-bottle med reconciliation for caregivers | Personal AI | High impact, but a wrong answer is dangerous and judges will ask about it. | ❌ |
| 9 | Visa RFE / immigration responder | Personal AI | Legal liability, and hard to demo with real documents. | ❌ |
| 10 | Lease red-flag scanner | Personal AI | Done many times before. | ❌ |
| 11 | Jetson home-robot agent | Physical AI | No hardware, no time. | ❌ |
| 12 | Scam-call real-time interceptor | Personal AI | Needs telephony and real-time audio, which is very hard to make reliable in 2 weeks. | ❌ |

## 3. Scoring the top 5

Scale 1-10. **Feasibility** = can one person ship a polished version by Oct 28. **Dev effort** = inverse effort (10 = light). **Impact** = real people, real money or harm. **Stand-out** = would a judge remember it after 200 submissions. **Tech showcase** = makes Nemotron, Token Factory and Tavily do something non-trivial. **Demo** = how well it lands in 3 minutes. **Fit** = your skills, interests and existing code.

| Idea | Feasibility | Dev effort | Impact | Stand-out | Tech showcase | Demo | Fit | **Total /70** |
|---|---|---|---|---|---|---|---|---|
| **1. Receipts** (claim → backtest) | 8 | 7 | 7 | **9** | **9** | **9** | **10** | **59** |
| **2. Denied** (insurance appeal) | 7 | 7 | **9** | 6 | 7 | 8 | 8 | **52** |
| **3. Bill Autopsy** | 6 | 6 | 9 | 7 | 7 | 8 | 8 | **51** |
| **4. Repro** (issue → failing test) | 6 | 5 | 7 | 6 | 9 | 6 | 6 | **45** |
| **5. Council Watch** | 7 | 6 | 7 | 7 | 6 | 6 | 5 | **44** |

### Why each one lands where it does

**2. Denied (52).** It has the biggest emotional impact. US insurers deny a large share of in-network claims, very few people appeal, and a large share of appeals win. But **it is a known hackathon idea**, and open-source appeal tools already exist, so it will feel familiar to judges. The hard part is that real policy documents are private PDFs, so the demo runs on synthetic letters.

**3. Bill Autopsy (51).** It has the same impact as #2 and is a bit fresher. The risk is the data: CPT code mapping and hospital price-transparency files are messy, huge, and inconsistent across hospitals. Expect to spend a week fighting JSON files instead of building the product.

**4. Repro (45).** It is the strongest pure-tech idea and fits the Coding track exactly. But it is also the **most crowded category in this hackathon**: half the field will build coding agents. And "it wrote a failing test" doesn't wow anyone in a 3-minute video.

**5. Council Watch (44).** It is a nice civic idea with natural Tavily use, but every city publishes agendas differently (PDF scans, Granicus, Legistar). The impact is real but slow, and nothing dramatic happens on screen.

**1. Receipts (59).** It wins on four of seven axes. Details below.

## 4. The pick: **Receipts**

> *"Every finance claim on the internet, turned into code and run. Show me the receipts."*

### The problem (impact)
Retail investors get their strategy ideas from finfluencers, YouTube, Reddit, newsletters and paid Discords. Claims like *"buy SPY when RSI < 30, 85% win rate"* or *"this options wheel makes 3% a month"* are almost never checked, because checking needs coding, data and backtesting skill. Regulators keep bringing finfluencer cases, but they can only act after the money is lost. **Nobody gives a normal person a 60-second way to check a claim before acting on it.**

### What it does (demo flow, in under 3 minutes)
1. **Paste** a claim: a tweet, a Reddit post, a YouTube transcript, or a URL.
2. **Extract (Nemotron Super):** the agent pulls out the *testable* hypothesis: instrument, entry rule, exit rule, period, the claimed metric, and what is left ambiguous. Instead of guessing silently, it shows an editable "here's how I read this claim" card.
3. **Research (Tavily):** it finds the original source, the author's past calls, any rebuttals, and whether the ticker even existed during the claimed period.
4. **Code (Nemotron as coding agent):** it writes the backtest. This is not freeform: it composes from the indicator, data and backtest primitives in `habibi/`.
5. **Execute (sandbox):** it runs the code on real historical data in an isolated sandbox, and **self-repairs** on errors (agent loop: write → run → read traceback → fix).
6. **Verdict card:** "Claimed 85% win rate → **Actual: 54%**, max drawdown −31%, underperformed buy-and-hold by 4.2%/yr", plus *why* the claim looked good (cherry-picked window, survivorship, ignored fees). It also includes an **honesty stress-test**: the same rule on other periods and tickers.
7. **Share:** a public receipt page with the code, data and chart, re-runnable by anyone.

### Why it beats the others on *your* criteria
- **Creative / non-cliché:** it is not a chatbot. It's an agent whose output is *a running experiment*. "LLM as falsification engine" is a fresh framing.
- **Powerful:** it uses all three of agentic code generation, tool use, and real execution, and the verdict comes from **real data, not the LLM's opinion**. That answers the hallucination question judges always ask.
- **Innovative:** it turns unstructured social claims into reproducible science artifacts, and the same pattern later works for health and diet claims, marketing claims, and more (good "future work" slide).
- **Feasible:** you already have a working data loader, indicators and a backtester in `habibi/`. That is roughly 40% of the hard engine already written and tested by you.
- **Hits every judge axis:** Tech (multi-model agent + sandbox + self-repair), Design (the verdict card is a great visual), Impact (consumer protection), Idea (memorable one-liner).
- **Prize stacking:** Grand prize contention + **Best Use of Tavily** (the research step is core to the product) + Coding/Agentic or Apps track.

### Main risks and how we handle them
| Risk | Mitigation |
|---|---|
| Claims are vague ("buy the dip") | Ambiguity is a feature: the agent shows its reading of the claim, and the user edits it before running. Ambiguous claims get the verdict *"unfalsifiable as stated"*, which is itself valuable. |
| LLM writes broken or unsafe code | Restricted DSL/primitives from `habibi/`, a sandbox, a retry loop capped at 3 attempts, and a fallback to a template strategy. |
| Token Factory Sandboxes not available or unclear | Fallback: a locked-down Docker runner on a Nebius AI Cloud VM (still satisfies "runs on Nebius"). |
| Options and crypto claims are harder | V1 covers **equities/ETFs + simple crypto only**. Options stay in "future work". |
| Look-ahead bias or fake precision | Hard-coded rules in the engine (next-bar fills, fees/slippage on by default), and the verdict always shows the assumptions. |
| "Financial advice" concern | Framing is *verification, not recommendation*. The output says "the claim does or doesn't hold", never "buy this". |

### Stack (proposed, confirm before building)
- **Models:** Nemotron 3 Super (planning, extraction, code) + Nemotron 3 Nano (cheap classification and summaries), via Nebius Token Factory (OpenAI-compatible).
- **Search:** Tavily API.
- **Engine:** Python, reusing `habibi/data.py`, `indicators.py` and `backtest.py`, with yfinance and crypto OHLCV.
- **Execution:** Token Factory sandbox, or a Docker runner on a Nebius VM.
- **App:** FastAPI backend + a single clean web UI (Next.js or plain HTML/Tailwind), with shareable receipt pages.

## 5. 14-day build plan

| Dates | Milestone |
|---|---|
| Oct 15-16 | Lock the idea. Sign up for the Nebius Builder Program (Token Factory + Tavily credits). Get Nemotron calls working. Check whether Token Factory Sandboxes exist. |
| Oct 17-19 | Claim → structured hypothesis extractor (JSON schema) plus 20 real test claims collected from Reddit/X/YouTube. |
| Oct 20-22 | Code-gen agent on `habibi` primitives + sandbox runner + self-repair loop. **Core end-to-end works by Oct 22.** |
| Oct 23-24 | Tavily research step (source, author history, rebuttals) + stress-test (other periods/tickers). |
| Oct 25-27 | UI: claim input → live agent trace → verdict card → shareable receipt page. Polish. |
| Oct 28 | Freeze features. README, license, architecture diagram. |
| Oct 29 | Record and edit the 3-min video. Write the Devpost text. |
| **Oct 30, before 10 AM PT** | Submit. (No new features after the 28th.) |

## 6. Decisions needed from you before we code
1. **Go with Receipts?** (Runner-up if you want pure impact: **Denied**.)
2. Solo, or a team (up to 4)? A teammate on UI/video would make Design much stronger.
3. Do you have Nebius Token Factory + Tavily accounts/credits yet?
4. Track to enter: **Best Apps & Agents** (broader) or **Coding & Agentic Engineering** (more technical, more crowded)? I'd go with Apps & Agents.
