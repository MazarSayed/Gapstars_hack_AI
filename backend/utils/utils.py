import json
import os
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DEFAULT_MODEL = "gemini-3.1-flash-lite"

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory by filename stem or full name."""
    filename = name if name.endswith(".md") else f"{name}.md"
    return (PROMPTS_DIR / filename).read_text()


def make_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def make_json_config(system_prompt: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
    )


def parse_json(raw: str) -> dict:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


async def stream_text_chunks(stream) -> AsyncGenerator[str, None]:
    """Yield non-empty text chunks from a Gemini streaming response."""
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
