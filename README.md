# Game Picker

An agentic-loop demo: a game recommendation agent built on the Claude API that
interprets a free-text request, decides for itself which of two public game
APIs to query (and which to skip), scores the candidates, self-checks the
result quality, and explains every decision in a live trace.

**Live:** https://game-picker-agent.netlify.app

## How it works

```
System prompt + skill file  +  4 tools  +  decision loop
```

1. The user describes what they want to play in plain language. Optional
   hints (genre, budget, platform, vibe) only fill gaps the text leaves open.
2. Claude (Haiku 4.5) reads the request, states its interpretation and picks a
   branch of the decision tree in `skills/game_analyzer.md`.
3. It calls tools as needed:
   - `search_free_games` / `get_free_game_details` (FreeToGame API)
   - `search_deals` / `search_game_by_title` (CheapShark API)
4. Tool results feed back into the next iteration. A quality gate can reject
   the agent's own scored results and force a broadened re-search.
5. The final answer is a scored, ranked recommendation plus a decision summary
   (branch taken, tools called, tools skipped, broadening rounds, price check).

The loop is non-deterministic: different inputs take visibly different tool
paths. See `SCENARIOS.md` for four inputs that exercise each branch and
`PLAN.md` for the design rationale.

## Architecture

| Piece | Where | Notes |
|---|---|---|
| Frontend | `static/` | Vanilla JS. Drives the loop: one `POST /api/step` per iteration, renders the SSE trace live. |
| Agent step (production) | `netlify/functions/step.ts` | Netlify Function. One Claude call + tool execution per request, streamed back as SSE. |
| Tools (TS) | `netlify/lib/tools.ts` | Port of `tools.py`. |
| System prompt (TS) | `netlify/lib/prompt.ts` + generated `skill.ts` | `scripts/gen-skill.mjs` embeds `skills/game_analyzer.md` at build time. |
| Agent (Python) | `agent.py`, `tools.py`, `system_prompt.py` | Same logic for the CLI and the Flask dev server. |
| Dev server | `server.py` | Flask. Serves `static/` and the same `/api/step` protocol. |
| CLI | `game_picker.py` | Interactive or one-shot runs in the terminal. |

Why per-step instead of running the whole loop in one request: Netlify
streaming functions are capped at 60 seconds, a full run can take longer, and
driving the loop from the browser keeps every request short while preserving
the live trace.

## Run locally

### Web UI with the Netlify Function (matches production)

```bash
npm install
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
npm run dev:web        # http://localhost:8888
```

### Web UI with the Flask dev server

```bash
pip3 install -r requirements.txt
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
python3 server.py      # http://localhost:3000
```

### CLI

```bash
python3 game_picker.py "something cozy like Stardew Valley under $15"
```

`.env` is gitignored and loaded only into the app process, never your shell.

## Deploy

The site is linked to Netlify (`game-picker-agent`). Set `ANTHROPIC_API_KEY`
in the Netlify project environment, then:

```bash
npx netlify-cli deploy --prod --build
```

Or connect the GitHub repo in the Netlify UI for automatic deploys on push.
The build command (`node scripts/gen-skill.mjs`) regenerates the skill module;
functions are bundled with esbuild on Node 22.
