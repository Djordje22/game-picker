"""
Web server for Game Picker — serves the frontend and streams agent events.

Local development only. The deployed site (Netlify) serves the same static
frontend and runs the agent in netlify/functions/step.ts, which speaks the
same per-step protocol as /api/step below.
"""

import json
import os

from flask import Flask, request, Response, send_from_directory, stream_with_context

from load_env import load_env
from agent import MAX_ITERATIONS, run_agent_step, run_agent_stream

app = Flask(__name__, static_folder="static")

# Load the key from the project-local .env into THIS process only (never global).
# Do not export ANTHROPIC_API_KEY in your shell: a global platform key makes Claude
# Code use it instead of your OAuth login. As an alternative to .env you can still
# pass it inline for a single run:
#   ANTHROPIC_API_KEY="sk-ant-..." python3 server.py
load_env()
API_KEY = os.environ.get("ANTHROPIC_API_KEY")

MAX_MESSAGES = 1 + MAX_ITERATIONS * 2
MAX_PROMPT_CHARS = 2000


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


def build_user_input(prompt: str, hints: dict) -> str:
    """
    Combine the free-text request with any optional hints into a single
    machine-readable message for the agent. This is the "clear machine
    readable input to start" that kicks off the agentic loop.

    The free text is the primary input. Hints only carry preferences the user
    explicitly set in the UI; unset hints are omitted entirely, and the skill
    instructs the agent that the free text wins on conflict.
    """
    hint_obj = {}
    for key in ("genre", "budget", "platform", "vibe"):
        value = str(hints.get(key, "")).strip()
        if value:
            hint_obj[key] = value

    request_obj = {"request": prompt.strip(), "hints": hint_obj}

    return (
        "Find me game recommendations for this request:\n"
        f"{json.dumps(request_obj, indent=2)}\n\n"
        "Interpret the request, follow your decision tree to pick tools, "
        "then score and rank your findings using the game analyzer rubric."
    )


def _sse(events):
    """Wrap an iterable of event dicts as a Server-Sent Events response."""
    def generate():
        for event in events:
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _missing_key_response():
    return {
        "error": "ANTHROPIC_API_KEY is not set. Start the server with "
        "ANTHROPIC_API_KEY=\"sk-ant-...\" python3 server.py"
    }, 500


@app.route("/api/step", methods=["POST"])
def step():
    """
    One iteration of the agentic loop. Same contract as the Netlify Function:

      first call:  {"prompt": "...", "hints": {...}}
      later calls: {"messages": [...]}   (from the previous step_done event)

    Streams trace events and ends with a step_done event carrying the
    updated conversation and whether the agent is done.
    """
    data = request.json or {}

    if not API_KEY:
        return _missing_key_response()

    messages = data.get("messages")
    if isinstance(messages, list) and messages:
        if len(messages) > MAX_MESSAGES or not all(
            isinstance(m, dict) and m.get("role") in ("user", "assistant") for m in messages
        ):
            return {"error": "Invalid conversation state"}, 400
    else:
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            return {"error": "Describe what you want to play (free-text request is required)"}, 400
        if len(prompt) > MAX_PROMPT_CHARS:
            return {"error": "Request is too long"}, 400
        hints = data.get("hints") or {}
        messages = [{"role": "user", "content": build_user_input(prompt, hints)}]

    return _sse(run_agent_step(messages, API_KEY))


@app.route("/api/recommend", methods=["POST"])
def recommend():
    """Legacy endpoint: runs the whole loop server-side in one streamed response."""
    data = request.json or {}

    prompt = str(data.get("prompt", "")).strip()
    hints = data.get("hints") or {}

    if not prompt:
        return {"error": "Describe what you want to play (free-text request is required)"}, 400

    if not API_KEY:
        return _missing_key_response()

    return _sse(run_agent_stream(build_user_input(prompt, hints), API_KEY))


if __name__ == "__main__":
    if not API_KEY:
        print(
            "\n  WARNING: ANTHROPIC_API_KEY is not set.\n"
            "  Start with:  ANTHROPIC_API_KEY=\"sk-ant-...\" python3 server.py\n"
            "  (Do not export it globally; put it in the project-local .env instead.)\n"
        )
    print("\n  Game Picker running at http://localhost:3000\n")
    app.run(host="0.0.0.0", port=3000, debug=False, threaded=True)
