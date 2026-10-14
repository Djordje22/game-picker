// Tool definitions and API wrappers for the Game Picker agent (TypeScript port of tools.py).
//
// Two data sources:
//   1. FreeToGame API  (free-to-play games)  https://www.freetogame.com/api-doc
//   2. CheapShark API  (paid game deals)     https://apidocs.cheapshark.com/
import type Anthropic from "@anthropic-ai/sdk";

export const TOOL_SCHEMAS: Anthropic.Tool[] = [
  {
    name: "search_free_games",
    description:
      "Search the Free-to-Play Games database. Returns a list of free games filtered by " +
      "platform and/or genre category. Use this when the user is open to free games or has a low budget.",
    input_schema: {
      type: "object",
      properties: {
        platform: {
          type: "string",
          description: "Platform filter: 'pc', 'browser', or 'all'",
          enum: ["pc", "browser", "all"],
        },
        category: {
          type: "string",
          description:
            "Genre/category filter. Options: mmorpg, shooter, strategy, moba, racing, sports, social, " +
            "sandbox, open-world, survival, pvp, pve, pixel, voxel, zombie, turn-based, first-person, " +
            "third-person, top-down, tank, space, sailing, side-scroller, superhero, permadeath, card, " +
            "battle-royale, mmo, mmofps, mmotps, 3d, 2d, anime, fantasy, sci-fi, fighting, action-rpg, " +
            "action, military, martial-arts, flight, low-spec, tower-defense, horror, mmorts",
        },
        sort_by: {
          type: "string",
          description: "Sort results by: 'release-date', 'popularity', 'alphabetical', or 'relevance'",
          enum: ["release-date", "popularity", "alphabetical", "relevance"],
        },
      },
      required: [],
    },
  },
  {
    name: "get_free_game_details",
    description:
      "Get detailed information about a specific free-to-play game by its ID. Returns full description, " +
      "screenshots, system requirements, and more. Use this after search_free_games to get deeper info on " +
      "promising candidates.",
    input_schema: {
      type: "object",
      properties: {
        game_id: { type: "integer", description: "The game ID from search_free_games results" },
      },
      required: ["game_id"],
    },
  },
  {
    name: "search_deals",
    description:
      "Search CheapShark for paid game deals across stores like Steam, GOG, and others. Returns games with " +
      "current prices, original prices, Steam ratings, and Metacritic scores. Use this when the user wants " +
      "paid games or wants to compare deals.",
    input_schema: {
      type: "object",
      properties: {
        upper_price: { type: "number", description: "Maximum price in USD (e.g. 20 for $20 max)" },
        lower_price: { type: "number", description: "Minimum price in USD (default 0)" },
        metacritic: {
          type: "integer",
          description: "Minimum Metacritic score (0-100). Use 70+ for well-reviewed games.",
        },
        steam_rating: { type: "integer", description: "Minimum Steam user rating percentage (0-100)" },
        sort_by: {
          type: "string",
          description: "Sort by: 'Deal Rating', 'Title', 'Savings', 'Price', 'Metacritic', 'Reviews', 'recent'",
          enum: ["Deal Rating", "Title", "Savings", "Price", "Metacritic", "Reviews", "recent"],
        },
        page_size: { type: "integer", description: "Number of results to return (max 60, default 10)" },
        on_sale: { type: "boolean", description: "Only show games currently on sale (default true)" },
      },
      required: [],
    },
  },
  {
    name: "search_game_by_title",
    description:
      "Search CheapShark for a specific game by title. Returns matching games with their cheapest current " +
      "price. Two uses: (1) anchor lookup, when the user names a game or asks for 'something like X'; " +
      "(2) price verification, to confirm your top paid pick's deal price is really the cheapest available " +
      "before finalizing.",
    input_schema: {
      type: "object",
      properties: {
        title: { type: "string", description: "Game title to search for (e.g. 'witcher', 'dark souls')" },
        limit: { type: "integer", description: "Max number of results (default 5)" },
      },
      required: ["title"],
    },
  },
];

const FREETOGAME_BASE = "https://www.freetogame.com/api";
const CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0";
const REQUEST_TIMEOUT_MS = 10_000;

type ToolInput = Record<string, unknown>;
type JsonValue = unknown;

/** Normalize an empty API response into an actionable signal instead of a bare []. */
function emptyResult(context: string): string {
  return JSON.stringify({
    results: [],
    note:
      `No matches for ${context}. Consider broadening: try a related genre, ` +
      "remove the platform filter, or try the other API.",
  });
}

function isErrorObject(data: JsonValue): data is { error: string } {
  return typeof data === "object" && data !== null && "error" in data;
}

async function httpGet(url: string): Promise<JsonValue> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "GamePicker/1.0", Accept: "application/json" },
      signal: controller.signal,
    });
    const text = await res.text();
    let parsed: JsonValue = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    if (!res.ok) {
      // FreeToGame answers "no games found" with a 404 and a JSON status object.
      if (parsed && typeof parsed === "object" && "status_message" in parsed) {
        return [];
      }
      return { error: `HTTP ${res.status}: ${res.statusText || "request failed"}` };
    }
    return parsed;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { error: `Connection failed: ${message}` };
  } finally {
    clearTimeout(timer);
  }
}

function num(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

async function searchFreeGames(params: ToolInput): Promise<string> {
  const query = new URLSearchParams();
  if (params.platform) query.set("platform", String(params.platform));
  if (params.category) query.set("category", String(params.category));
  if (params.sort_by) query.set("sort-by", String(params.sort_by));

  const qs = query.toString();
  const url = `${FREETOGAME_BASE}/games${qs ? `?${qs}` : ""}`;
  const data = await httpGet(url);

  if (isErrorObject(data)) return JSON.stringify(data);
  if (!Array.isArray(data) || data.length === 0) {
    return emptyResult(`free games with filters ${qs || "none"}`);
  }
  // Return first 15 results to keep context manageable.
  return JSON.stringify(data.slice(0, 15), null, 2);
}

async function getFreeGameDetails(params: ToolInput): Promise<string> {
  const gameId = num(params.game_id, NaN);
  if (!Number.isFinite(gameId)) return JSON.stringify({ error: "game_id must be a number" });
  const data = await httpGet(`${FREETOGAME_BASE}/game?id=${gameId}`);
  return JSON.stringify(data, null, 2);
}

async function searchDeals(params: ToolInput): Promise<string> {
  const query = new URLSearchParams();
  if (params.upper_price != null) query.set("upperPrice", String(params.upper_price));
  if (params.lower_price != null) query.set("lowerPrice", String(params.lower_price));
  if (params.metacritic != null) query.set("metacritic", String(params.metacritic));
  if (params.steam_rating != null) query.set("steamRating", String(params.steam_rating));
  if (params.sort_by) query.set("sortBy", String(params.sort_by));
  query.set("pageSize", String(params.page_size ? Math.min(num(params.page_size, 10), 60) : 10));
  if (params.on_sale != null) query.set("onSale", params.on_sale ? "1" : "0");
  // Always use store 1 (Steam) for consistency.
  query.set("storeID", "1");

  const data = await httpGet(`${CHEAPSHARK_BASE}/deals?${query.toString()}`);
  if (isErrorObject(data)) return JSON.stringify(data);

  const items: Array<Record<string, unknown>> = Array.isArray(data)
    ? data.slice(0, 15)
    : data && typeof data === "object"
      ? [data as Record<string, unknown>]
      : [];
  if (items.length === 0) return emptyResult("paid game deals with these filters");

  const simplified = items.map((deal) => ({
    title: deal.title,
    sale_price: `$${deal.salePrice ?? "N/A"}`,
    normal_price: `$${deal.normalPrice ?? "N/A"}`,
    savings_percent: `${Math.round(num(deal.savings))}%`,
    metacritic_score: deal.metacriticScore ?? "N/A",
    steam_rating_percent: deal.steamRatingPercent ?? "N/A",
    steam_rating_text: deal.steamRatingText ?? "N/A",
    deal_rating: deal.dealRating ?? "N/A",
    thumb: deal.thumb ?? "",
  }));
  return JSON.stringify(simplified, null, 2);
}

async function searchGameByTitle(params: ToolInput): Promise<string> {
  const title = String(params.title ?? "").trim();
  if (!title) return JSON.stringify({ error: "title is required" });
  const limit = params.limit != null ? num(params.limit, 5) : 5;
  const query = new URLSearchParams({ title, limit: String(limit) });
  const data = await httpGet(`${CHEAPSHARK_BASE}/games?${query.toString()}`);
  if (Array.isArray(data) && data.length === 0) return emptyResult(`games titled '${title}'`);
  return JSON.stringify(data, null, 2);
}

const TOOL_EXECUTORS: Record<string, (params: ToolInput) => Promise<string>> = {
  search_free_games: searchFreeGames,
  get_free_game_details: getFreeGameDetails,
  search_deals: searchDeals,
  search_game_by_title: searchGameByTitle,
};

/** Execute a tool by name and return its result as a string (never throws). */
export async function executeTool(toolName: string, toolInput: unknown): Promise<string> {
  const executor = TOOL_EXECUTORS[toolName];
  if (!executor) return JSON.stringify({ error: `Unknown tool: ${toolName}` });
  const params: ToolInput =
    toolInput && typeof toolInput === "object" ? (toolInput as ToolInput) : {};
  try {
    return await executor(params);
  } catch (err) {
    return JSON.stringify({ error: err instanceof Error ? err.message : String(err) });
  }
}
