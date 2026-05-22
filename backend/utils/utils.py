import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langfuse import get_client as _get_langfuse_client
from langfuse import propagate_attributes  # re-exported for other modules

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash"

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_langfuse = None


def get_langfuse():
    global _langfuse
    if _langfuse is None:
        _langfuse = _get_langfuse_client()
    return _langfuse


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


def _build_lf_input(contents: str, config: types.GenerateContentConfig) -> list[dict]:
    """Build a Langfuse-style message list from Gemini call args."""
    messages = []
    system = getattr(config, "system_instruction", None)
    if system:
        messages.append({"role": "system", "content": str(system)})
    messages.append({"role": "user", "content": contents})
    return messages


async def traced_stream_chunks(
    client: genai.Client,
    *,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    name: str,
) -> AsyncGenerator[str, None]:
    """Stream Gemini output while recording a Langfuse generation observation with retries on transient errors."""
    lf = get_langfuse()
    max_retries = 3
    initial_delay = 1.0
    
    for attempt in range(max_retries + 1):
        started_yielding = False
        accumulated = ""
        try:
            with lf.start_as_current_observation(
                as_type="generation",
                name=name,
                model=model,
                input=_build_lf_input(contents, config),
            ) as obs:
                stream = await client.aio.models.generate_content_stream(
                    model=model, contents=contents, config=config,
                )
                async for chunk in stream_text_chunks(stream):
                    started_yielding = True
                    accumulated += chunk
                    yield chunk
                obs.update(output=accumulated)
                return
        except Exception as e:
            is_transient = "503" in str(e) or "UNAVAILABLE" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "limit" in str(e).lower()
            if attempt < max_retries and is_transient and not started_yielding:
                delay = initial_delay * (2 ** attempt)
                print(f"[RETRY] Streaming attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise e


async def traced_generate(
    client: genai.Client,
    *,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    name: str,
) -> str:
    """Call Gemini non-streaming while recording a Langfuse generation observation with retries on transient errors."""
    lf = get_langfuse()
    max_retries = 3
    initial_delay = 1.0
    
    for attempt in range(max_retries + 1):
        try:
            with lf.start_as_current_observation(
                as_type="generation",
                name=name,
                model=model,
                input=_build_lf_input(contents, config),
            ) as obs:
                response = await client.aio.models.generate_content(
                    model=model, contents=contents, config=config,
                )
                text = response.text.strip()
                obs.update(output=text)
                return text
        except Exception as e:
            is_transient = "503" in str(e) or "UNAVAILABLE" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "limit" in str(e).lower()
            if attempt < max_retries and is_transient:
                delay = initial_delay * (2 ** attempt)
                print(f"[RETRY] Non-streaming attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise e
