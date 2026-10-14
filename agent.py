"""
The agentic loop — the core of the Game Picker app.

This is a simplified version of the pattern used in support-agent (Clay):
  1. Send user message + tools to Claude
  2. If Claude responds with tool_use → execute tools → feed results back → loop
  3. If Claude responds with text only → that's the final answer → stop
"""

import anthropic

from system_prompt import SYSTEM_PROMPT
from tools import TOOL_SCHEMAS, execute_tool

MAX_ITERATIONS = 15  # safety cap to prevent runaway loops
MODEL = "claude-haiku-4-5-20251001"


def run_agent(user_input: str, api_key: str) -> str:
    """
    Run the agentic loop for a single user request.

    Returns the agent's final text response.
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Conversation history starts with the user's message
    messages = [{"role": "user", "content": user_input}]

    iteration = 0
    tool_calls = []  # every tool name called, in order — the run's decision trace

    while iteration < MAX_ITERATIONS:
        iteration += 1

        print(f"\n{'='*60}")
        print(f"  AGENT LOOP — Iteration {iteration}")
        print(f"{'='*60}")

        # Call Claude with the system prompt, tools, and conversation so far
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Check what Claude returned
        has_tool_use = any(
            block.type == "tool_use" for block in response.content
        )

        # Process each content block (text and/or tool calls)
        assistant_content = []
        tool_results = []

        for block in response.content:
            if block.type == "text":
                # Claude is thinking or giving its final answer
                print(f"\n  Agent says:\n{_indent(block.text)}")
                assistant_content.append(block)

            elif block.type == "tool_use":
                # Claude wants to call a tool
                tool_calls.append(block.name)
                print(f"\n  Tool call: {block.name}")
                print(f"  Input: {block.input}")

                # Execute the tool
                result = execute_tool(block.name, block.input)
                print(f"  Result preview: {result[:200]}...")

                assistant_content.append(block)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        # Add the assistant's response to conversation history
        messages.append({"role": "assistant", "content": assistant_content})

        # If there were tool calls, add results and loop back
        if has_tool_use and tool_results:
            messages.append({"role": "user", "content": tool_results})
            print(f"\n  → Feeding {len(tool_results)} tool result(s) back to agent...")
            continue

        # No tool calls — Claude gave its final answer
        final_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        )

        if response.stop_reason == "end_turn":
            print(f"\n{'='*60}")
            print(f"  AGENT DONE — {iteration} iteration(s)")
            print(f"  RUN SUMMARY")
            print(f"    Iterations:   {iteration}")
            print(f"    Tools called: {' -> '.join(tool_calls) if tool_calls else 'none'}")
            print(f"{'='*60}")
            return final_text

        # Unexpected stop reason — return what we have
        print(f"\n  Unexpected stop_reason: {response.stop_reason}")
        return final_text

    # Hit the iteration cap
    print(f"\n  WARNING: Hit max iterations ({MAX_ITERATIONS})")
    return "I ran out of steps before completing my analysis. Please try a more specific request."


def run_agent_step(messages: list, api_key: str):
    """
    ONE iteration of the agentic loop — yields event dicts.

    This is the same protocol the Netlify Function (netlify/functions/step.ts)
    speaks, so the web frontend works identically against this dev server and
    the deployed site. The caller owns the loop: it feeds the `messages` from
    the final `step_done` event back in until `done` is true.
    """
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}
        return

    has_tool_use = any(b.type == "tool_use" for b in response.content)
    assistant_content = []
    tool_results = []

    for block in response.content:
        if block.type == "text":
            event_type = "thinking" if has_tool_use else "answer"
            yield {"type": event_type, "text": block.text}
            assistant_content.append({"type": "text", "text": block.text})

        elif block.type == "tool_use":
            yield {"type": "tool_call", "name": block.name, "input": block.input}
            result = execute_tool(block.name, block.input)
            yield {"type": "tool_result", "name": block.name, "preview": result[:500]}
            assistant_content.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

    next_messages = list(messages) + [{"role": "assistant", "content": assistant_content}]

    if has_tool_use and tool_results:
        next_messages.append({"role": "user", "content": tool_results})
        yield {"type": "step_done", "done": False, "messages": next_messages}
        return

    yield {
        "type": "step_done",
        "done": True,
        "messages": next_messages,
        "stop_reason": response.stop_reason,
    }


def run_agent_stream(user_input, api_key):
    """
    Streaming version of the full agentic loop — yields event dicts.

    Kept for the legacy /api/recommend endpoint; the web UI now uses the
    per-step protocol (run_agent_step) so it can run on serverless hosting.
    """
    messages = [{"role": "user", "content": user_input}]
    tool_calls = []  # every tool name called, in order — the run's decision trace

    for iteration in range(1, MAX_ITERATIONS + 1):
        yield {"type": "iteration_start", "iteration": iteration}

        done = False
        for event in run_agent_step(messages, api_key):
            if event["type"] == "step_done":
                messages = event["messages"]
                done = event["done"]
                continue
            if event["type"] == "tool_call":
                tool_calls.append(event["name"])
            if event["type"] == "error":
                yield event
                return
            yield event

        if done:
            yield {"type": "run_summary", "iterations": iteration, "tool_calls": tool_calls}
            yield {"type": "done", "iterations": iteration}
            return

    yield {"type": "error", "message": "Max iterations reached"}


def _indent(text: str, prefix: str = "    ") -> str:
    """Indent every line of text for readable logging."""
    return "\n".join(prefix + line for line in text.split("\n"))
