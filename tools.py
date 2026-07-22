"""
Tool definitions and API wrappers for the Game Picker agent.

Two data sources:
  1. FreeToGame API  — free-to-play games (https://www.freetogame.com/api-doc)
  2. CheapShark API  — paid game deals   (https://apidocs.cheapshark.com/)
"""

import json
import urllib.request
import urllib.parse
import urllib.error

# ---------------------------------------------------------------------------
# Tool schemas — these are sent to Claude so it knows how to call each tool
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "search_free_games",
        "description": (
            "Search the Free-to-Play Games database. Returns a list of free "
            "games filtered by platform and/or genre category. Use this when "
            "the user is open to free games or has a low budget."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform filter: 'pc', 'browser', or 'all'",
                    "enum": ["pc", "browser", "all"],
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Genre/category filter. Options: mmorpg, shooter, "
                        "strategy, moba, racing, sports, social, sandbox, "
                        "open-world, survival, pvp, pve, pixel, voxel, "
                        "zombie, turn-based, first-person, third-person, "
                        "top-down, tank, space, sailing, side-scroller, "
                        "superhero, permadeath, card, battle-royale, mmo, "
                        "mmofps, mmotps, 3d, 2d, anime, fantasy, sci-fi, "
                        "fighting, action-rpg, action, military, "
                        "martial-arts, flight, low-spec, tower-defense, "
                        "horror, mmorts"
                    ),
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort results by: 'release-date', 'popularity', 'alphabetical', or 'relevance'",
                    "enum": ["release-date", "popularity", "alphabetical", "relevance"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_free_game_details",
        "description": (
            "Get detailed information about a specific free-to-play game by "
            "its ID. Returns full description, screenshots, system "
            "requirements, and more. Use this after search_free_games to get "
            "deeper info on promising candidates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {
                    "type": "integer",
                    "description": "The game ID from search_free_games results",
                },
            },
            "required": ["game_id"],
        },
    },
    {
        "name": "search_deals",
        "description": (
            "Search CheapShark for paid game deals across stores like Steam, "
            "GOG, and others. Returns games with current prices, original "
            "prices, Steam ratings, and Metacritic scores. Use this when the "
            "user wants paid games or wants to compare deals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "upper_price": {
                    "type": "number",
                    "description": "Maximum price in USD (e.g. 20 for $20 max)",
                },
                "lower_price": {
                    "type": "number",
                    "description": "Minimum price in USD (default 0)",
                },
                "metacritic": {
                    "type": "integer",
                    "description": "Minimum Metacritic score (0-100). Use 70+ for well-reviewed games.",
                },
                "steam_rating": {
                    "type": "integer",
                    "description": "Minimum Steam user rating percentage (0-100)",
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort by: 'Deal Rating', 'Title', 'Savings', 'Price', 'Metacritic', 'Reviews', 'recent'",
                    "enum": ["Deal Rating", "Title", "Savings", "Price", "Metacritic", "Reviews", "recent"],
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results to return (max 60, default 10)",
                },
                "on_sale": {
                    "type": "boolean",
                    "description": "Only show games currently on sale (default true)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_game_by_title",
        "description": (
            "Search CheapShark for a specific game by title. Returns matching "
            "games with their cheapest current price. Two uses: (1) anchor "
            "lookup, when the user names a game or asks for 'something like "
            "X'; (2) price verification, to confirm your top paid pick's deal "
            "price is really the cheapest available before finalizing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Game title to search for (e.g. 'witcher', 'dark souls')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results (default 5)",
                },
            },
            "required": ["title"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations — actual API calls
# ---------------------------------------------------------------------------

_FREETOGAME_BASE = "https://www.freetogame.com/api"
_CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"


def _empty_result(context: str) -> str:
    """
    Normalize an empty API response into an actionable signal instead of a
    bare []. The note nudges the agent into its broadening branch.
    """
    return json.dumps({
        "results": [],
        "note": (
            f"No matches for {context}. Consider broadening: try a related "
            "genre, remove the platform filter, or try the other API."
        ),
    })


def _http_get(url: str):
    """Simple GET request that returns parsed JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": "GamePicker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"error": f"Connection failed: {exc.reason}"}
    except Exception as exc:
        return {"error": str(exc)}


def execute_search_free_games(params: dict) -> str:
    """Search FreeToGame API for free-to-play games."""
    query = {}
    if params.get("platform"):
        query["platform"] = params["platform"]
    if params.get("category"):
        query["category"] = params["category"]
    if params.get("sort_by"):
        query["sort-by"] = params["sort_by"]

    url = f"{_FREETOGAME_BASE}/games"
    if query:
        url += "?" + urllib.parse.urlencode(query)

    data = _http_get(url)

    if isinstance(data, dict) and "error" in data:
        return json.dumps(data)

    if not isinstance(data, list) or not data:
        # FreeToGame returns a status object (or nothing) when no games match
        return _empty_result(
            f"free games with filters {query or 'none'}"
        )

    # Return first 15 results to keep context manageable
    return json.dumps(data[:15], indent=2)


def execute_get_free_game_details(params: dict) -> str:
    """Get detailed info for a specific free game."""
    game_id = params["game_id"]
    url = f"{_FREETOGAME_BASE}/game?id={game_id}"
    data = _http_get(url)
    return json.dumps(data, indent=2)


def execute_search_deals(params: dict) -> str:
    """Search CheapShark for paid game deals."""
    query = {}
    if params.get("upper_price") is not None:
        query["upperPrice"] = params["upper_price"]
    if params.get("lower_price") is not None:
        query["lowerPrice"] = params["lower_price"]
    if params.get("metacritic") is not None:
        query["metacritic"] = params["metacritic"]
    if params.get("steam_rating") is not None:
        query["steamRating"] = params["steam_rating"]
    if params.get("sort_by"):
        query["sortBy"] = params["sort_by"]
    if params.get("page_size"):
        query["pageSize"] = min(params["page_size"], 60)
    else:
        query["pageSize"] = 10
    if params.get("on_sale") is not None:
        query["onSale"] = 1 if params["on_sale"] else 0

    # Always use store 1 (Steam) for consistency
    query["storeID"] = 1

    url = f"{_CHEAPSHARK_BASE}/deals?" + urllib.parse.urlencode(query)
    data = _http_get(url)

    if isinstance(data, dict) and "error" in data:
        return json.dumps(data)

    items = data[:15] if isinstance(data, list) else [data] if isinstance(data, dict) else []
    if not items:
        return _empty_result("paid game deals with these filters")

    # Simplify the response to key fields
    simplified = []
    for deal in items:
        simplified.append({
            "title": deal.get("title"),
            "sale_price": f"${deal.get('salePrice', 'N/A')}",
            "normal_price": f"${deal.get('normalPrice', 'N/A')}",
            "savings_percent": f"{float(deal.get('savings', 0)):.0f}%",
            "metacritic_score": deal.get("metacriticScore", "N/A"),
            "steam_rating_percent": deal.get("steamRatingPercent", "N/A"),
            "steam_rating_text": deal.get("steamRatingText", "N/A"),
            "deal_rating": deal.get("dealRating", "N/A"),
            "thumb": deal.get("thumb", ""),
        })

    return json.dumps(simplified, indent=2)


def execute_search_game_by_title(params: dict) -> str:
    """Search CheapShark for a game by title."""
    title = params["title"]
    limit = params.get("limit", 5)
    query = urllib.parse.urlencode({"title": title, "limit": limit})
    url = f"{_CHEAPSHARK_BASE}/games?{query}"
    data = _http_get(url)

    if isinstance(data, list) and not data:
        return _empty_result(f"games titled '{title}'")

    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool dispatcher — maps tool name to its executor
# ---------------------------------------------------------------------------

TOOL_EXECUTORS = {
    "search_free_games": execute_search_free_games,
    "get_free_game_details": execute_get_free_game_details,
    "search_deals": execute_search_deals,
    "search_game_by_title": execute_search_game_by_title,
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by name and return its result as a string."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return executor(tool_input)
