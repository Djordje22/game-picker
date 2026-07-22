"""
Minimal .env loader that keeps the Anthropic key project-scoped.

It reads KEY=value pairs from a .env file next to this module and injects them
into os.environ for THIS process only. It never touches your shell and never
overrides a variable that is already set in the environment.

Why this exists (Bryan's #ask-it note, 2026-07-20): if ANTHROPIC_API_KEY is set
globally in your shell, Claude Code uses that platform key instead of your OAuth
login (authentication precedence). Loading the key from a gitignored .env that
only this app reads means the key is present when you run Game Picker and nowhere
else.
"""

import os

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


def load_env(path: str = _ENV_PATH) -> None:
    """Load KEY=value lines from `path` into os.environ without overriding
    variables already set. Does nothing if the file is missing."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
