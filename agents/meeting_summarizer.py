import json
from pathlib import Path
from google import genai
from google.genai import types
from schema.meeting_schema import MeetingSummary

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "summarizer_prompt.md"
SUMMARIZER_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


async def run_meeting_summarizer(client: genai.Client, transcript: str) -> MeetingSummary:
    """Agent 1: Extracts discussion points, decisions, and produces a concise meeting summary."""
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=f"Please summarize the following meeting transcript:\n\n{transcript}",
        config=types.GenerateContentConfig(
            system_instruction=SUMMARIZER_SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    return MeetingSummary(**data)
