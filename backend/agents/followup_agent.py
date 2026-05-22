import json
from typing import AsyncGenerator
from google import genai
from utils import DEFAULT_MODEL, load_prompt, make_json_config, stream_text_chunks

_CONFIG = make_json_config(load_prompt("followup_prompt"))


async def stream_followup_agent(
    client: genai.Client, summary: dict, action_report: dict
) -> AsyncGenerator[str, None]:
    contents = (
        f"Meeting Summary:\n{json.dumps(summary, indent=2)}\n\n"
        f"Action Item Report:\n{json.dumps(action_report, indent=2)}"
    )
    stream = await client.aio.models.generate_content_stream(
        model=DEFAULT_MODEL,
        contents=contents,
        config=_CONFIG,
    )
    async for chunk in stream_text_chunks(stream):
        yield chunk
