from typing import AsyncGenerator
from google import genai
from utils import DEFAULT_MODEL, load_prompt, make_json_config, traced_stream_chunks

_CONFIG = make_json_config(load_prompt("summarizer_prompt"))


async def stream_meeting_summarizer(client: genai.Client, transcript: str) -> AsyncGenerator[str, None]:
    """Yields raw JSON text chunks as they arrive from the model."""
    contents = f"Please summarize the following meeting transcript:\n\n{transcript}"
    async for chunk in traced_stream_chunks(
        client, model=DEFAULT_MODEL, contents=contents, config=_CONFIG, name="meeting-summarizer"
    ):
        yield chunk