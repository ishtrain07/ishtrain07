# NVDA Hackathon: Ideation v3 (broad sweep)

**Event:** Nebius x NVIDIA Global AI Hackathon (Devpost)
**Deadline:** Oct 30, 2026, 10:00 AM PT (from search results quoting Devpost; verify on the site)
**Status:** ideation only. No code until the idea is locked.

## 0. What went wrong in v1 and v2
- **v1 (Receipts, a finance claim auditor):** clever, but nobody would use it weekly.
- **v2 (Invoice Watch):** practical, but 4 of the top 5 were the *same pattern*: read a document, find a discrepancy, draft a letter to recover money. That was anchoring, not a broad search.

## 1. Method for v3
I swept **12 domains**, and for each one asked which *interaction pattern* fits best, so the shortlist covers different shapes, not five versions of one. The patterns:
- **Write-run-test** (code that proves itself)
- **Vision** (photos and handwriting)
- **Voice** (spoken notes)
- **Background agent** (watches and acts)
- **Research** (live web)

Filter for every idea:
- A named user with a recurring pain
- Explainable in one sentence
- A visible outcome on screen
- Not cliché
- Shippable solo by Oct 28 on Token Factory + Nemotron with a hosted URL

## 2. Broad longlist (24 ideas, 12 domains)

| Domain | Idea | Pattern | One sentence | Verdict |
|---|---|---|---|---|
| **Accessibility** | **Curb Cut** | write-run-test | Point it at your website; it finds accessibility failures, fixes the source code, and proves the fix by re-running the audit. | ✅ |
| Accessibility | "Explain this letter" in your language | vision + voice | Explains official letters in the reader's own language. | ❌ done often |
| **Education** | **Misconception Map** | vision | Snap a class set of quiz answers; it groups wrong answers by the *misunderstanding* behind them and writes tomorrow's reteach plan. | ✅ |
| Education | AI tutor | chat | A chat tutor. | ❌ cliché |
| **Health / care** | **Caregiver Log** | voice + background | A family caregiver talks for 30 seconds a day; it spots patterns (sleep, falls, missed meds) and writes a one-page brief for the next doctor visit. | ✅ |
| Health | Insurance denial appeals | document | Drafts appeals for denied claims. | ❌ already exists |
| Health | Physio form-checker via webcam | real-time vision | Checks exercise form on camera. | ❌ real-time reliability risk |
| **Small business** | Invoice Watch (v2 pick) | vision + document | Catches supplier overcharges on invoices. | ✅ kept as benchmark |
| Small business | Sheet Lint (spreadsheet linter) | write-run-test | Finds errors in business spreadsheets. | ❌ less emotional |
| **Dev tools** | Flaky Test Hunter | write-run-test | Runs the suite repeatedly, isolates flaky tests, finds the root cause. | ⚠️ judges are devs, but narrow impact |
| Dev tools | Dependency-upgrade agent | write-run-test | Upgrades a library and fixes what breaks. | ❌ crowded (Dependabot, Copilot) |
| **Civic** | 311 Fix-it | vision + research | Photo of a pothole or broken light → right agency, filled form, follow-up tracked. | ⚠️ |
| Civic | City-council watcher | research | Alerts you when council agendas affect you. | ❌ messy data |
| **Personal finance** | Trade-journal coach (uses your `habibi` trades) | background | Reads your trade log and names the habit that costs you money. | ⚠️ small audience |
| Personal finance | Finance claim auditor (v1 pick, Receipts) | write-run-test | Turns finance claims into backtests. | ❌ low recurring use |
| **Sports** | Youth-coach scouting reports from box scores | research | Writes scouting reports from public box scores. | ❌ thin data |
| Sports | Rec-league stats from phone video | video | Keeps stats from phone video. | ❌ too hard in 12 days |
| **Housing** | Deposit Defender | vision | Builds the evidence pack to get a rental deposit back. | ❌ same document pattern, used once per move |
| **Climate / energy** | Utility bill + rebate stacker | document | Finds energy rebates from your utility bill. | ❌ same document pattern |
| Climate | Home energy waste finder | data | Spots what's wasting power at home. | ❌ needs smart-meter data |
| **Research / science** | Paper figure → data → re-plot | vision + code | Pulls data out of paper figures and re-plots it. | ❌ too niche |
| **Work / ops** | SOP from screen recording | video | Turns a screen recording into a written procedure. | ❌ video pipeline too heavy |
| **Personal AI** | Promise tracker ("you told Sam you'd send X") | background | Tracks commitments you made in your messages. | ⚠️ needs private message access |
| **Physical AI** | Anything | sim/hardware | Robotics or sensor projects. | ❌ no hardware or time |

## 3. Top 5 across different patterns (1-10 each, /60)

| Idea | Pattern | Feasibility | Real pain | Explain | Stand-out | Tech | Demo | **Total** |
|---|---|---|---|---|---|---|---|---|
| **Curb Cut** (a11y fixer) | write-run-test | 8 | 8 | 9 | 8 | **10** | 9 | **52** |
| Invoice Watch | vision + document | 8 | 9 | 9 | 8 | 8 | 9 | **51** |
| **Misconception Map** | vision | 7 | 8 | **10** | **9** | 7 | 9 | **50** |
| Caregiver Log | voice + background | 6 | **9** | 9 | 7 | 6 | 7 | **44** |
| 311 Fix-it | vision + research | 7 | 6 | 9 | 6 | 6 | 7 | **41** |

The top three are within 2 points of each other, so the scores alone don't decide. Here's the honest case for each.

### Curb Cut: accessibility fixer that proves its fixes (52)
- **User:** web devs, agencies and small businesses. Many sites fail basic accessibility checks, which locks out people with disabilities and creates legal exposure (ADA demand letters are common in the US).
- **What it does:**
  1. Crawls the site and runs an automated accessibility audit (axe-core) in a sandbox.
  2. Nemotron writes source-level fixes: alt text from the actual image, labels, contrast, focus order, ARIA.
  3. Re-runs the audit to *prove* each fix, then opens a PR.
- **Why it stands out:** today's "AI accessibility" market is mostly overlay widgets that critics say don't really fix anything. Curb Cut **fixes the code itself and proves it**. The name comes from the curb-cut effect: accessibility helps everyone.
- **Stack fit:** this is word for word what the Coding track asks for ("write, run, and test code"):
  - Nano VL writes alt text from the actual images.
  - Super writes the code fixes.
  - Ultra reviews the diff.
  - Serverless Jobs runs the crawls.
- **Demo:** score 54 → 96, then a screen reader reading a page that was gibberish before and makes sense after.
- **Risk:** the Coding track is the most crowded. Complex JavaScript frameworks are harder to fix, so the demo targets static or React sites.

### Misconception Map: for teachers (50)
- **User:** K-12 teachers, every week. Grading tells a teacher *who* got it wrong, not *why*.
- **What it does:**
  1. The teacher photographs or uploads a class set of answers (handwritten or a Google Forms export).
  2. The model groups wrong answers by underlying misconception, e.g. "11 students think 1/3 > 1/2 because 3 > 2".
  3. It writes a 10-minute reteach plan and 3 targeted practice questions per group.
- **Why it stands out:** it's the most creative and most human of the set, it is not a tutor chatbot, and the teacher stays in charge.
- **Risk:** reading handwriting is the hardest technical part. Mitigation: support typed and Forms exports first, handwriting second. Real student data needs care, so demo with synthetic quizzes.

### Invoice Watch: restaurant supplier leaks (51)
- Still a strong option. It's the most practical and has the clearest dollar figure, but it's the least exciting to engineers judging tech.

## 4. Recommendation
**Curb Cut** if you want the best mix of **feasible + technically impressive + real impact**. The proof loop (audit → fix → re-audit) is deterministic, so the demo can't be faked or fall apart, and it matches the track brief exactly.

**Misconception Map** if you want the most **creative and emotional** story and are OK with handwriting risk.

## 5. Decisions needed from you
1. Curb Cut, Misconception Map, or Invoice Watch? (Or is there a domain you care about that I should dig into further, like sports or healthcare?)
2. Solo or team?
3. OK to create a new public repo for the submission?

Build plan, stack and submission checklist get written once the idea is locked.

## Appendix: official rules that shape the idea
- Must run on **Nebius Token Factory or AI Cloud** and use **≥1 NVIDIA open model** (Nemotron).
- Apps & Agents track wants Ultra for heavy reasoning, Nano/Super for fast calls, and optionally Serverless Endpoints and Jobs. The Coding track wants agents that write, run and test code in Token Factory.
- Required: working demo URL, public YouTube video ≤3 min showing Token Factory + Nemotron, public repo with an OSS license, README with Nemotron/Token Factory/Nebius usage, feedback, and a disclosure of pre-existing code.
- Judging (equal weight): Technological Implementation · Design · Potential Impact · Quality of Idea.
