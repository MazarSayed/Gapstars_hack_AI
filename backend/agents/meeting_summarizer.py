from pathlib import Path
from typing import AsyncGenerator
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "summarizer_prompt.md"
SUMMARIZER_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_CONFIG = types.GenerateContentConfig(
    system_instruction=SUMMARIZER_SYSTEM_PROMPT,
    response_mime_type="application/json",
)


async def stream_meeting_summarizer(client: genai.Client, transcript: str) -> AsyncGenerator[str, None]:
    """Yields raw JSON text chunks as they arrive from the model."""
    stream = await client.aio.models.generate_content_stream(
        model=MODEL,
        contents=f"Please summarize the following meeting transcript:\n\n{transcript}",
        config=_CONFIG,
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
