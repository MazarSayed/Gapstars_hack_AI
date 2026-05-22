from pathlib import Path
from typing import AsyncGenerator
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "action_item_prompt.md"
ACTION_ITEM_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_CONFIG = types.GenerateContentConfig(
    system_instruction=ACTION_ITEM_SYSTEM_PROMPT,
    response_mime_type="application/json",
)


async def stream_action_item_agent(client: genai.Client, transcript: str) -> AsyncGenerator[str, None]:
    """Yields raw JSON text chunks as they arrive from the model."""
    stream = await client.aio.models.generate_content_stream(
        model=MODEL,
        contents=f"Please extract all action items from the following meeting transcript:\n\n{transcript}",
        config=_CONFIG,
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
