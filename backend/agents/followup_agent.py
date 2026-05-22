import json
from typing import AsyncGenerator
from google import genai
from utils import DEFAULT_MODEL, load_prompt, make_json_config, traced_stream_chunks

_CONFIG = make_json_config(load_prompt("followup_prompt"))


async def stream_followup_agent(
    client: genai.Client, summary: dict, action_report: dict
) -> AsyncGenerator[str, None]:
    contents = (
        f"Meeting Summary:\n{json.dumps(summary, indent=2)}\n\n"
        f"Action Item Report:\n{json.dumps(action_report, indent=2)}"
    )
    async for chunk in traced_stream_chunks(
        client, model=DEFAULT_MODEL, contents=contents, config=_CONFIG, name="followup-email-drafter"
    ):
        yield chunk
