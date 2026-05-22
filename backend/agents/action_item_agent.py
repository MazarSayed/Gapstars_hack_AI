from typing import AsyncGenerator
from google import genai
from utils import DEFAULT_MODEL, load_prompt, make_json_config, stream_text_chunks

_CONFIG = make_json_config(load_prompt("action_item_prompt"))


async def stream_action_item_agent(client: genai.Client, transcript: str) -> AsyncGenerator[str, None]:
    """Yields raw JSON text chunks as they arrive from the model."""
    stream = await client.aio.models.generate_content_stream(
        model=DEFAULT_MODEL,
        contents=f"Please extract all action items from the following meeting transcript:\n\n{transcript}",
        config=_CONFIG,
    )
    async for chunk in stream_text_chunks(stream):
        yield chunk
