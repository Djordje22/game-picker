#!/usr/bin/env python3
"""
Game Picker — An agentic loop mini app.

Demonstrates the agentic loop pattern:
  System Prompt + Skill File + Tools (APIs) + Decision Loop

Usage:
  python game_picker.py                         # interactive mode
  python game_picker.py "RPG under $20, relaxing"  # one-shot mode
"""

import json
import sys
import os

from load_env import load_env
from agent import run_agent

# Load the key from the project-local .env into THIS process only (never global).
# Do not export ANTHROPIC_API_KEY in your shell: a global platform key makes Claude
# Code use it instead of your OAuth login. As an alternative to .env you can still
# pass it inline for a single run:
#   ANTHROPIC_API_KEY="sk-ant-..." python3 game_picker.py
# Need a key? Request one in the #ask-it Slack channel.
load_env()
API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def build_user_input(prompt: str, hints: dict) -> str:
    """
    Combine the free-text request with any optional hints into a single
    machine-readable message. The free text is the primary input; hints only
    carry preferences the user explicitly set (unset ones are omitted).
    """
    request_obj = {
        "request": prompt.strip(),
        "hints": {k: v for k, v in hints.items() if v},
    }
    return (
        f"Find me game recommendations for this request:\n"
        f"{json.dumps(request_obj, indent=2)}\n\n"
        f"Interpret the request, follow your decision tree to pick tools, "
        f"then score and rank your findings using the game analyzer rubric."
    )


def interactive_mode():
    """Prompt the user for a free-text request (plus optional hints) and run the agent."""
    print("\n" + "=" * 60)
    print("  GAME PICKER — Agentic Loop Demo")
    print("=" * 60)
    print("\nDescribe what you want to play, in your own words.")
    print('Example: "something cozy like Stardew Valley under $15"\n')

    prompt = ""
    while not prompt:
        prompt = input("  Your request: ").strip()

    print("\n  Optional hints (press Enter to skip any of them):\n")
    hints = {
        "genre": input("  Genre hint (e.g. RPG, shooter, MMORPG): ").strip(),
        "budget": input("  Budget hint (e.g. 20, or 'free'): ").strip(),
        "platform": input("  Platform hint (pc / browser / all): ").strip(),
        "vibe": input("  Vibe hint (relaxing / competitive / story-driven / social): ").strip(),
    }

    user_input = build_user_input(prompt, hints)

    print("\n" + "-" * 60)
    print("  INPUT TO AGENT:")
    print("-" * 60)
    print(user_input)
    print("-" * 60)

    result = run_agent(user_input, API_KEY)

    print("\n" + "=" * 60)
    print("  FINAL RECOMMENDATION")
    print("=" * 60)
    print(result)


def one_shot_mode(query: str):
    """Run the agent with a single query string."""
    print(f"\n  Query: {query}\n")
    result = run_agent(query, API_KEY)

    print("\n" + "=" * 60)
    print("  FINAL RECOMMENDATION")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    if not API_KEY:
        print(
            "\n  ERROR: ANTHROPIC_API_KEY is not set.\n"
            "  Run with:  ANTHROPIC_API_KEY=\"sk-ant-...\" python3 game_picker.py\n"
            "  (Do not export it globally; request a key in #ask-it.)\n"
        )
        sys.exit(1)

    if len(sys.argv) > 1:
        one_shot_mode(" ".join(sys.argv[1:]))
    else:
        interactive_mode()
