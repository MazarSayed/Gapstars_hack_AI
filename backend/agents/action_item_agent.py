import json
from pathlib import Path
from google import genai
from google.genai import types
from schema.meeting_schema import ActionItemReport

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "action_item_prompt.md"
ACTION_ITEM_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


async def run_action_item_agent(client: genai.Client, transcript: str) -> ActionItemReport:
    """Agent 2: Extracts action items, owners, due dates, and flags missing information."""
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=f"Please extract all action items from the following meeting transcript:\n\n{transcript}",
        config=types.GenerateContentConfig(
            system_instruction=ACTION_ITEM_SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    return ActionItemReport(**data)
