# Game Picker — Agentic Loop Improvement Plan

Goal: make the app demonstrably **non-deterministic, non-programmatic, autonomous,
self-correcting, and non-linear** — so that different inputs produce visibly
different tool paths, and tool results can change the agent's next decision.

The mentor's three test questions this plan must answer with "yes":

1. *Are any of those tools ever NOT called?* → yes: whole APIs get skipped
   depending on the request (see Scenarios 1 and 2).
2. *Do the tools have any relation to each other?* → yes: ID chaining, anchor-game
   flow, and price cross-checking feed one tool's output into another tool's input.
3. *Is there a feedback loop?* → yes: a quality gate can reject the agent's own
   scored results and force a broadened re-search before answering.

Guiding principle (Getting Real): the fix is mostly **words, not machinery**.
Phases 1–3 are prompt/skill edits, Phase 4 is a small input-model change,
Phase 5 is a tiny logging addition, Phase 6 is documentation. No new
dependencies, no new architecture.

---

## Phase 1 — Skill rewrite (`skills/game_analyzer.md`) — the core change

### 1.1 Step 1 becomes "Interpret the request" (free text first)

- The primary input is a **free-text request**. The agent extracts genre, budget,
  platform, vibe, and any *anchor game* ("something like Stardew Valley") from
  the text itself.
- Optional structured `hints` (from the select menus) only fill gaps the text
  leaves open. **If text and hints conflict, the text wins.**
- If a preference is genuinely unknowable, the agent states its assumption
  explicitly and proceeds (autonomous — it never stalls waiting for input).

### 1.2 New decision tree with real branching

Replace the current linear flowchart with branches keyed on the interpreted
request. Each branch must name tools that are **deliberately skipped**:

```
Did the user name a specific game or say "something like X"?
  YES → START with search_game_by_title (anchor lookup)
        → derive genre/vibe from the anchor
        → then continue below with the derived preferences
  NO  → continue

Is budget "free" / $0?
  YES → search_free_games ONLY. Never call search_deals. (skip = a decision)
  NO  → continue

Is budget generous (>= $40) or intent clearly "premium / story-driven / AAA"?
  YES → START with search_deals. Only check free games if paid results
        score poorly (< 3 candidates at 25/40 after scoring).
  NO  → probe BOTH sources, then narrow to whichever returns stronger matches.
```

**Delete the "always try BOTH APIs" key rule** — it is the single biggest
reason the current version behaves deterministically.

### 1.3 Cross-validation rule (tool → tool feedback)

Before finalizing: for the **top paid candidate**, call `search_game_by_title`
to confirm the deal price is actually the cheapest available.

- If a cheaper price exists → correct the price, re-score Budget Fit, note the
  correction in the output.
- This makes one tool's *result* trigger another tool's *call* — a genuine
  feedback edge, not a fixed sequence.

### 1.4 Quality gate (self-correction that actually fires)

After scoring, before producing output:

```
Do at least 3 candidates score >= 25/40?
  NO → do NOT answer yet. Broaden and re-search, in this order:
       round 1: related genre (e.g. "sailing" → "open-world", "adventure")
       round 2: drop the platform filter / relax the rating filter
       max 2 broadening rounds, then answer honestly with the best available
       and say the results are weak.
  YES → proceed to output.
```

### 1.5 Detail-check rule

If a top-3 free candidate is missing description/requirements needed for the
Vibe Match score → call `get_free_game_details` for it first. (ID chaining:
output of search feeds input of details.)

### 1.6 Output format additions

Extend `DECISION SUMMARY` with:

```
Tools called:  [list, in order]
Tools skipped: [list, each with a one-line reason]
Broadening rounds: [0/1/2]
Assumptions made: [anything inferred from vague input]
```

The "tools skipped + why" line is the direct, visible answer to the mentor's
first question on every single run.

---

## Phase 2 — System prompt (`system_prompt.py`)

- **Remove** the rule "Use BOTH free and paid game sources unless…".
- **Add**: "Choose tools according to the decision tree in your skill. Calling
  a tool is a decision; NOT calling a tool is also a decision — record both
  in the decision summary."
- **Add**: "Before your first tool call, state your interpretation of the
  request: extracted preferences, assumptions, and which branch of the
  decision tree you are taking." (traceability)
- Add `search_game_by_title` back into the tools overview with its two roles:
  anchor-game lookup, and final price cross-check.

---

## Phase 3 — Input model flip (server + CLI + UI)

### 3.1 `server.py`

- `/api/recommend` accepts `{ "prompt": "<free text>", "hints": { genre?, budget?, platform?, vibe? } }`.
  `prompt` is the primary field; `hints` optional.
- `build_user_input` produces a machine-readable envelope (keeps the doc's
  "clear machine readable input" constraint):

```json
{
  "request": "something cozy like Stardew Valley, under $15",
  "hints": { "platform": "pc" }
}
```

  Only hints the user actually set are included. Remove the "Search both …
  sources" sentence from the template — the skill decides that now.

### 3.2 `static/` (index.html, app.js)

- Textarea for the free-text request becomes the primary control.
- The four selects move under an "Optional hints" section, all defaulting to
  "not specified"; unset hints are simply omitted from the payload.

### 3.3 `game_picker.py` (CLI)

- Interactive mode: first ask "Describe what you want to play:", then offer
  the four hint questions with Enter-to-skip.
- One-shot mode already takes free text — unchanged.

---

## Phase 4 — Tools (`tools.py`) — minimal touch

- `search_game_by_title` already exists; keep it. Improve its description to
  name both roles (anchor lookup, price verification).
- Normalize empty results: when an API returns `[]`, return
  `{"results": [], "note": "no matches - consider broadening genre or removing filters"}`
  instead of a bare empty list, so the model gets an actionable recovery signal.
- No other tool changes. Do NOT add new tools.

---

## Phase 5 — Trace/reliability instrumentation (`agent.py`) — ~15 lines

- Track `tool_calls: list[str]` across the loop.
- On completion, print / yield a final structured event:
  `{ "type": "run_summary", "iterations": N, "tool_calls": [...] }`.
- This is the raw material for the reliability metric in Phase 6 — no other
  code needed.

---

## Phase 6 — `SCENARIOS.md` (inputs → expected outputs)

Five canned inputs, each exercising a different branch. For each: the input,
the expected tool path, and the expected loop shape.

| # | Input | Expected path | Demonstrates |
|---|-------|--------------|--------------|
| 1 | "free MMORPG for a low-spec PC" | `search_free_games` (+ details); **deals skipped** | conditional skipping |
| 2 | "story-driven single-player RPG, happy to pay up to $60" | `search_deals` first → `search_game_by_title` price check; **free skipped or briefly probed** | branch + cross-validation |
| 3 | "something like Stardew Valley under $15" | `search_game_by_title` (anchor) → derived genre → both APIs | anchor flow, tool→tool dependency |
| 4 | "relaxing sailing game for browser" | sparse results → **broadening round(s)** → answer | self-correction, non-linear |
| 5 | "cheap co-op zombie shooter with good reviews" | deals with metacritic filter + free zombie/pvp search → compare | qualitative→quantitative scoring across sources |

### Reliability check (quantitative, per the exercise doc)

- Run each scenario 3–5 times; record `run_summary` (iterations, tool_calls)
  and the top pick.
- Metrics: **consistency** = same #1 pick (or ≥2/3 overlap in top-3) across
  runs; **path stability** = same branch taken. Record results in a small
  table at the bottom of SCENARIOS.md. Manual runs are fine — no harness
  needed.

---

## Implementation order

1. Phase 1 + 2 (skill + system prompt) — biggest behavioral win, zero code.
2. Phase 3 (input flip) — makes non-determinism reachable from the UI/CLI.
3. Phase 4 + 5 (empty-result signal, run summary) — small code.
4. Phase 6 (scenarios + reliability table) — run and record.

## Acceptance checklist (the "answer is yes" test)

- [ ] At least two scenarios skip an entire API, and the output says so and why.
- [ ] At least one scenario shows a tool call whose input came from a previous
      tool's output (anchor or price check).
- [ ] At least one scenario visibly triggers the quality gate and re-searches
      before answering.
- [ ] Same free-text input phrased two different ways can take different paths
      (non-deterministic, non-programmatic).
- [ ] Every run's output lists tools called, tools skipped, assumptions, and
      broadening rounds (traceable decision making).
- [ ] SCENARIOS.md documents inputs → expected outputs, plus a reliability
      table from repeated runs.
