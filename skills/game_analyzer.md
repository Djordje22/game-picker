---
name: game-analyzer
description: >
  Skill file for analyzing and scoring games based on a free-text request.
  Defines request interpretation, the branching decision tree, cross-validation,
  the quality gate, the scoring rubric, and the recommendation format.
---

# Game Analyzer Skill

## Purpose

You use this skill to interpret a free-text game request, decide which tools to
call (and which to deliberately skip), score the games you find, self-check your
results, and produce a final recommendation.

## Step 1: Interpret the Request

Your primary input is a **free-text request** written by the user. Optional
structured `hints` may accompany it, but only for preferences the user set
explicitly.

Extract these from the request text:

| Preference   | Example Values                        | If not stated              |
|--------------|---------------------------------------|----------------------------|
| genre        | RPG, shooter, MMORPG, strategy, etc.  | infer from context or "any"|
| budget       | number in USD, "free", "cheap"        | no limit, note assumption  |
| platform     | pc, browser                           | pc                         |
| vibe         | relaxing, competitive, story-driven   | infer from wording         |
| anchor game  | "something like Stardew Valley"       | none                       |

Rules of interpretation:

- **The free text always wins over hints.** Hints only fill gaps the text
  leaves open. If the text says "free game" and a hint says budget $60, the
  budget is free.
- If a preference is genuinely unknowable, make a reasonable assumption,
  **state it explicitly**, and proceed. Never stall waiting for more input.
- Before your first tool call, state your interpretation: extracted
  preferences, assumptions made, and which branch of the decision tree below
  you are taking.

## Step 2: Decide Which Tools to Call

This is where your agentic reasoning matters. Calling a tool is a decision;
NOT calling a tool is also a decision. You will report both at the end.

### Decision Tree

```
START
  |
  v
Did the user name a specific game, or say "something like X"?
  YES --> ANCHOR BRANCH:
          call search_game_by_title with the anchor game
          --> derive genre and vibe from what you know about the anchor
          --> continue below using the derived preferences
  NO  --> continue
  |
  v
Is the budget "free" / $0?
  YES --> FREE BRANCH:
          call search_free_games ONLY (filter by genre + platform).
          Do NOT call search_deals. Skipping it is the correct decision here.
  NO  --> continue
  |
  v
Is the budget generous (>= $40) or the intent clearly premium
(story-driven single-player, AAA, "best game money can buy")?
  YES --> PREMIUM BRANCH:
          start with search_deals (price, metacritic filters).
          Only call search_free_games if the paid results are weak
          (fewer than 3 candidates scoring >= 25/40).
  NO  --> MIXED BRANCH:
          probe BOTH sources, then narrow to whichever returns
          stronger matches for the request.
```

### Detail check

If a top-3 free candidate is missing the description or details you need for
the Vibe Match score, call `get_free_game_details` for it before scoring.

### Cross-validation (mandatory before finalizing)

If your #1 recommendation is a **paid** game, call `search_game_by_title` with
its title to confirm the deal price you found is actually the cheapest
available right now.

- If a cheaper price exists: correct the price, re-score Budget Fit, and note
  the correction in your output.
- If it matches: say the price was verified.

## Step 3: Quality Gate (self-check before answering)

After scoring all candidates, check: **do at least 3 candidates score
25/40 or higher?**

If NO, do not answer yet. Broaden and re-search:

1. Round 1: try a closely related genre (e.g. "sailing" has no matches, try
   "open-world" or "adventure"), or relax the rating filter.
2. Round 2: drop the platform filter, or raise the price ceiling slightly and
   flag the over-budget picks.

Run at most 2 broadening rounds. If results are still weak, answer honestly
with the best you found and say the results are weak, suggesting how the user
could adjust their request.

## Step 4: Scoring Rubric

Score each game on four dimensions (0-10 each, max total = 40):

### Genre Match (0-10)
- 10: exact genre match (user wants "RPG", game is "RPG")
- 7-9: closely related genre (user wants "RPG", game is "Action RPG" or "MMORPG")
- 4-6: loosely related (user wants "RPG", game is "Strategy" with RPG elements)
- 0-3: poor match

### Budget Fit (0-10)
- 10: free game when budget is low, or price is < 50% of budget
- 7-9: price is within budget with room to spare
- 5-6: price is close to budget limit
- 3-4: slightly over budget but worth mentioning
- 0-2: way over budget
- For free games: always 10

### Rating Score (0-10)
- Normalize from available data:
  - Steam rating: divide percentage by 10 (e.g., 85% = 8.5)
  - Metacritic: divide by 10 (e.g., 78 = 7.8)
  - If no rating data: assign 5 (neutral) and note "unrated"
- If both Steam and Metacritic exist, average them

### Vibe Match (0-10)
- YOU judge this based on the game's description, genre, and your knowledge
- "relaxing" = low-stress, exploration, creativity, cozy
- "competitive" = PvP, ranked, esports, fast-paced
- "story-driven" = narrative focus, single-player, cinematic
- "social" = co-op, MMO, team-based
- "hardcore" = difficult, punishing, skill-based
- If no vibe specified or inferable: assign 7 to all (neutral-positive)

## Step 5: Output Format

Present your recommendations in this exact structure. IMPORTANT: never use em
dashes, use colons or commas instead.

```
RECOMMENDATIONS
===============

Interpreted request: [genre], [budget], [platform], [vibe]
Assumptions: [anything you inferred, or "none"]

#1: [Game Name] (Score: [X]/40)
    Source: [Free-to-Play / CheapShark Deal]
    Genre: [genre] | Price: [price, note if verified or corrected] | Rating: [rating info]

    Genre Match:  [X]/10, [one-line reason]
    Budget Fit:   [X]/10, [one-line reason]
    Rating Score: [X]/10, [one-line reason]
    Vibe Match:   [X]/10, [one-line reason]

    Why this game: [2-3 sentence summary of why it's a good pick]

#2: [Game Name] (Score: [X]/40)
    ... (same format)

#3: [Game Name] (Score: [X]/40)
    ... (same format)

FREE ALTERNATIVE (if applicable):
    [Game Name] (Score: [X]/40)
    ... (same format, highlighting it's free)

DECISION SUMMARY:
    Branch taken: [ANCHOR / FREE / PREMIUM / MIXED]
    Tools called: [list, in the order you called them]
    Tools skipped: [each skipped tool with a one-line reason, or "none"]
    Broadening rounds: [0 / 1 / 2, and what you changed each round]
    Price check: [verified / corrected from $X to $Y / not applicable]
    Searched [N] games, filtered to [M] candidates.
    Top pick scores [X]/40, beating runner-up by [Y] points.
    Key differentiator: [what made #1 stand out].
```

## Important Notes

- Always explain WHY you chose to call each tool, and WHY you skipped the ones
  you skipped. This demonstrates agentic reasoning.
- If an empty result includes a note suggesting you broaden the search, treat
  that as a signal to take a broadening round, not as a dead end.
- If results are poor after broadening, say so honestly and suggest the user
  adjust their request.
- Never fabricate game data, only use what the APIs return.
- When comparing free vs paid games, be explicit about the trade-offs.
