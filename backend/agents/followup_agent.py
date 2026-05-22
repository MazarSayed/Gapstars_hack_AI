import json
from pathlib import Path
from typing import AsyncGenerator
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "followup_prompt.md"
FOLLOWUP_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_CONFIG = types.GenerateContentConfig(
    system_instruction=FOLLOWUP_SYSTEM_PROMPT,
    response_mime_type="application/json",
)


async def stream_followup_agent(
    client: genai.Client, summary: dict, action_report: dict
) -> AsyncGenerator[str, None]:
    contents = (
        f"Meeting Summary:\n{json.dumps(summary, indent=2)}\n\n"
        f"Action Item Report:\n{json.dumps(action_report, indent=2)}"
    )
    stream = await client.aio.models.generate_content_stream(
        model=MODEL,
        contents=contents,
        config=_CONFIG,
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
