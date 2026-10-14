// One iteration of the agentic loop, as a Netlify Function.
//
// The browser drives the loop: it POSTs the conversation so far, this function
// makes exactly one Claude call, executes any tools Claude asked for, streams
// the trace events back (Server-Sent Events), and finishes with a `step_done`
// event carrying the updated conversation. The browser then either calls again
// (Claude asked for tools) or renders the final answer.
//
// Why per-step instead of running the whole loop here: Netlify streaming
// functions are capped at 60 seconds, while a full run can take longer. One
// Claude call plus a couple of API lookups comfortably fits.
import Anthropic from "@anthropic-ai/sdk";
import type { Config, Context } from "@netlify/functions";

import { SYSTEM_PROMPT, buildUserInput } from "../lib/prompt";
import { TOOL_SCHEMAS, executeTool } from "../lib/tools";

const MODEL = "claude-haiku-4-5-20251001";
const MAX_TOKENS = 4096;
const MAX_ITERATIONS = 15;
// user + (assistant + tool results) per iteration
const MAX_MESSAGES = 1 + MAX_ITERATIONS * 2;
const MAX_BODY_BYTES = 1_500_000;
const MAX_PROMPT_CHARS = 2_000;

type TraceEvent =
  | { type: "thinking"; text: string }
  | { type: "answer"; text: string }
  | { type: "tool_call"; name: string; input: unknown }
  | { type: "tool_result"; name: string; preview: string }
  | { type: "step_done"; done: boolean; messages: Anthropic.MessageParam[]; stop_reason?: string | null }
  | { type: "error"; message: string };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

function isMessageParam(value: unknown): value is Anthropic.MessageParam {
  if (!value || typeof value !== "object") return false;
  const m = value as { role?: unknown; content?: unknown };
  if (m.role !== "user" && m.role !== "assistant") return false;
  return typeof m.content === "string" || Array.isArray(m.content);
}

async function runStep(
  client: Anthropic,
  messages: Anthropic.MessageParam[],
  send: (event: TraceEvent) => void,
): Promise<void> {
  const response = await client.messages.create({
    model: MODEL,
    max_tokens: MAX_TOKENS,
    system: [{ type: "text", text: SYSTEM_PROMPT, cache_control: { type: "ephemeral" } }],
    tools: TOOL_SCHEMAS,
    messages,
  });

  if (response.stop_reason === "refusal") {
    send({ type: "error", message: "The model declined this request. Try rephrasing it." });
    return;
  }

  const hasToolUse = response.content.some((block) => block.type === "tool_use");
  const toolResults: Anthropic.ToolResultBlockParam[] = [];

  for (const block of response.content) {
    if (block.type === "text") {
      send({ type: hasToolUse ? "thinking" : "answer", text: block.text });
    } else if (block.type === "tool_use") {
      send({ type: "tool_call", name: block.name, input: block.input });
      const result = await executeTool(block.name, block.input);
      send({ type: "tool_result", name: block.name, preview: result.slice(0, 500) });
      toolResults.push({ type: "tool_result", tool_use_id: block.id, content: result });
    }
  }

  const next: Anthropic.MessageParam[] = [...messages, { role: "assistant", content: response.content }];

  if (hasToolUse && toolResults.length > 0) {
    // All tool results for one assistant turn go back in a single user message.
    next.push({ role: "user", content: toolResults });
    send({ type: "step_done", done: false, messages: next });
    return;
  }

  send({ type: "step_done", done: true, messages: next, stop_reason: response.stop_reason });
}

export default async (req: Request, _context: Context) => {
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return json({ error: "ANTHROPIC_API_KEY is not configured on the server." }, 500);
  }

  const raw = await req.text();
  if (raw.length > MAX_BODY_BYTES) return json({ error: "Request too large" }, 413);

  let body: { prompt?: unknown; hints?: unknown; messages?: unknown };
  try {
    body = JSON.parse(raw || "{}");
  } catch {
    return json({ error: "Body must be JSON" }, 400);
  }

  let messages: Anthropic.MessageParam[];
  if (Array.isArray(body.messages) && body.messages.length > 0) {
    if (body.messages.length > MAX_MESSAGES || !body.messages.every(isMessageParam)) {
      return json({ error: "Invalid conversation state" }, 400);
    }
    messages = body.messages;
  } else {
    const prompt = String(body.prompt ?? "").trim();
    if (!prompt) {
      return json({ error: "Describe what you want to play (free-text request is required)" }, 400);
    }
    if (prompt.length > MAX_PROMPT_CHARS) return json({ error: "Request is too long" }, 400);
    const hints = body.hints && typeof body.hints === "object" ? (body.hints as Record<string, unknown>) : {};
    messages = [{ role: "user", content: buildUserInput(prompt, hints) }];
  }

  const client = new Anthropic({ apiKey, maxRetries: 1 });
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: TraceEvent) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
      };
      try {
        await runStep(client, messages, send);
      } catch (err) {
        let message = "Unexpected error";
        if (err instanceof Anthropic.AuthenticationError) message = "Invalid Anthropic API key on the server.";
        else if (err instanceof Anthropic.RateLimitError) message = "Rate limited by the Claude API, try again shortly.";
        else if (err instanceof Anthropic.APIError) message = `Claude API error ${err.status}: ${err.message}`;
        else if (err instanceof Error) message = err.message;
        send({ type: "error", message });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
};

export const config: Config = {
  path: "/api/step",
};
