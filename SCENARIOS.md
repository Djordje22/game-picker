# Game Picker — Demo Scenarios

Each scenario exercises a different branch of the agent's decision tree.
Together they show that the tool path depends on the input (non-deterministic,
non-programmatic), that tools feed each other (non-linear), and that the agent
can reject its own results and retry (self-correcting).

Run from the CLI:

```bash
ANTHROPIC_API_KEY="sk-ant-..." python3 game_picker.py "<scenario input>"
```

or paste the input into the web UI textarea (leave all hints unset).

---

## Scenario 1 — Free branch (tools get skipped)

**Input:** `free MMORPG for a low-spec PC`

**Expected path:**
- Branch: FREE
- `search_free_games` (category mmorpg or low-spec, platform pc), possibly
  `get_free_game_details` for top candidates
- `search_deals` is **never called**, and the decision summary says why
- ~2-3 iterations

**Demonstrates:** conditional tool skipping. Answers the mentor's
"are any of those ever NOT called?" with a visible yes.

## Scenario 2 — Premium branch + price cross-check

**Input:** `story-driven single-player RPG, happy to pay up to $60`

**Expected path:**
- Branch: PREMIUM
- `search_deals` first (upper_price 60, metacritic filter)
- `search_game_by_title` on the #1 paid pick to verify the price
- `search_free_games` skipped (or only probed if paid results are weak)

**Demonstrates:** branching + cross-validation, where one tool's *result*
(the top deal) becomes another tool's *input* (the title to verify).

## Scenario 3 — Anchor branch (tool-to-tool dependency)

**Input:** `something like Stardew Valley but under $15`

**Expected path:**
- Branch: ANCHOR
- `search_game_by_title` ("stardew valley") first, to anchor genre/vibe/price
- Derived preferences (cozy, sandbox/simulation, relaxing) drive
  `search_deals` (upper_price 15) and/or `search_free_games`
- Price check on the top paid pick

**Demonstrates:** the first tool call's output shapes every later call.

## Scenario 4 — Quality gate / self-correction

**Input:** `relaxing sailing game for browser`

**Expected path:**
- Branch: MIXED
- First searches (sailing + browser) return few or no matches; empty results
  come back with a "consider broadening" note
- Agent takes 1-2 broadening rounds: related genre (open-world, adventure),
  then drops the platform filter
- Decision summary reports `Broadening rounds: 1` or `2`
- More iterations than the happy path (4+)

**Demonstrates:** self-correction and a non-linear loop; the agent refuses to
answer from weak results.

## Scenario 5 — Mixed branch, cross-source scoring

**Input:** `cheap co-op zombie shooter with good reviews`

**Expected path:**
- Branch: MIXED
- `search_deals` (low upper_price, steam_rating/metacritic filter) AND
  `search_free_games` (zombie / shooter / pvp)
- Free and paid candidates scored on the same 0-40 rubric and compared
  explicitly

**Demonstrates:** qualitative preferences ("cheap", "good reviews", "co-op
vibe") turned into quantitative filters and scores.

---

## Reliability check (repeated runs)

The exercise doc asks for a quantitative reliability measure. Run each
scenario 3-5 times and record the `RUN SUMMARY` (iterations + tool order,
printed by the CLI and shown in the web trace) plus the #1 pick.

Metrics:

- **Path stability:** same branch taken across runs (target: 100%)
- **Pick consistency:** same #1 pick, or at least 2/3 overlap in the top 3
- **Iteration spread:** min-max iterations per scenario

Results below are from a real run on 2026-07-21 (model claude-haiku-4-5),
recorded from each run's `RUN SUMMARY`. Full logs are under `runs/`.

| Scenario | Run | Branch  | Tools called (summarized)                                | Iters | #1 pick |
|----------|-----|---------|----------------------------------------------------------|-------|---------|
| 1 (free) | 1   | FREE    | search_free_games -> get_free_game_details x5            | 3     | Digimon Masters Online |
| 1 (free) | 2   | FREE    | search_free_games x2 -> get_free_game_details x7         | 4     | Cabal Online |
| 2 (prem) | 1   | PREMIUM | search_deals -> search_game_by_title (price check)       | 3     | Disco Elysium: The Final Cut |
| 2 (prem) | 2   | PREMIUM | search_deals -> search_game_by_title x3 (price checks)   | 3     | Disco Elysium: The Final Cut |
| 3 (anch) | 1   | ANCHOR  | search_game_by_title -> search_deals -> search_free_games -> many title checks | 9 | Only Farming: Cozy Harvesting Game |
| 4 (self) | 1   | FREE    | 5x search_free_games (broadening) -> details -> title/deals probes | 11 | none: honest "no true match" |

Observations:

- **Path stability:** the branch is 100% stable across repeated runs (scenario
  1 always FREE with deals skipped; scenario 2 always PREMIUM with a price
  check). This is the "reliability / consistency" metric from the exercise doc.
- **Pick consistency:** scenario 2 returned the exact same #1 (Disco Elysium)
  both runs. Scenario 1 returned different #1 picks (Digimon vs Cabal) but both
  are low-spec MMORPGs from the same candidate pool: strong top-3 overlap,
  weaker #1 stability. Worth noting as the least deterministic scenario.
- **Iteration spread:** happy-path branches finish in 3-4 iterations; the
  anchor and self-correction scenarios run 9-11, because tool results keep
  changing the next decision (non-linear).
- **Self-correction confirmed:** scenario 4 hit empty results, followed the
  "consider broadening" note through several rounds across both APIs, and then
  answered honestly that no true match exists rather than fabricating one.

Differences in wording between runs are expected. What stays stable is the
branch, the skip decisions, and the quality of the candidate pool.
