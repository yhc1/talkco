import json
import logging

from openai import AsyncOpenAI

from config import settings

log = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def chat_json(system_prompt: str, user_message: str) -> dict:
    """Call GPT-4o with JSON response format and return parsed dict."""
    resp = await _client.chat.completions.create(
        model=settings.CHAT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    text = resp.choices[0].message.content
    log.debug("chat_json response: %s", text[:500])
    return json.loads(text)
