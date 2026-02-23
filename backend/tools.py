import json

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "search_news",
        "description": "Search for recent news articles on a given topic. Use when the user asks about news or current events.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query for news articles",
                }
            },
            "required": ["query"],
        },
    }
]


def _search_news(query: str) -> str:
    articles = [
        {
            "title": f"Latest developments in {query}",
            "summary": f"Experts report significant progress in {query} this week, with new findings suggesting positive trends ahead.",
            "source": "Global Times",
        },
        {
            "title": f"{query}: What you need to know",
            "summary": f"A comprehensive overview of recent events related to {query}, including expert analysis and public reactions.",
            "source": "Daily Report",
        },
    ]
    return json.dumps(articles)


def execute_tool(name: str, args: dict) -> str:
    if name == "search_news":
        return _search_news(args.get("query", ""))
    return json.dumps({"error": f"Unknown tool: {name}"})
