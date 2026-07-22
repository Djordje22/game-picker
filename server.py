"""
Web server for Game Picker — serves the frontend and streams agent events.
"""

import json
import os

from flask import Flask, request, Response, send_from_directory, stream_with_context

from load_env import load_env
from agent import run_agent_stream

app = Flask(__name__, static_folder="static")

# Load the key from the project-local .env into THIS process only (never global).
# Do not export ANTHROPIC_API_KEY in your shell: a global platform key makes Claude
# Code use it instead of your OAuth login. As an alternative to .env you can still
# pass it inline for a single run:
#   ANTHROPIC_API_KEY="sk-ant-..." python3 server.py
# Need a key? Request one in the #ask-it Slack channel.
load_env()
API_KEY = os.environ.get("ANTHROPIC_API_KEY")


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


@app.route("/api/recommend", methods=["POST"])
def recommend():
    data = request.json or {}

    prompt = str(data.get("prompt", "")).strip()
    hints = data.get("hints") or {}

    if not prompt:
        return {"error": "Describe what you want to play (free-text request is required)"}, 400

    user_input = build_user_input(prompt, hints)

    if not API_KEY:
        return {
            "error": "ANTHROPIC_API_KEY is not set. Start the server with "
            "ANTHROPIC_API_KEY=\"sk-ant-...\" python3 server.py "
            "(request a key in #ask-it)."
        }, 500

    def generate():
        for event in run_agent_stream(user_input, API_KEY):
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


if __name__ == "__main__":
    if not API_KEY:
        print(
            "\n  WARNING: ANTHROPIC_API_KEY is not set.\n"
            "  Start with:  ANTHROPIC_API_KEY=\"sk-ant-...\" python3 server.py\n"
            "  (Do not export it globally; request a key in #ask-it.)\n"
        )
    print("\n  Game Picker running at http://localhost:3000\n")
    app.run(host="0.0.0.0", port=3000, debug=False, threaded=True)
