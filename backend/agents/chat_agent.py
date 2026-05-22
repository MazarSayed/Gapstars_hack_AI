import json
from pathlib import Path
from typing import AsyncGenerator
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "chat_prompt.md"
CHAT_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


async def stream_chat_agent(
    client: genai.Client,
    message: str,
    history: list,  # list of dicts, e.g. [{"role": "user", "content": "..."}, {"role": "model", "content": "..."}]
    transcript: str = "",
    analysis_results: dict = None,
) -> AsyncGenerator[str, None]:
    # Construct context block
    context = ""
    if transcript:
        context += f"Transcript:\n{transcript}\n\n"
    if analysis_results:
        context += f"Analysis Results:\n{json.dumps(analysis_results, indent=2)}\n\n"

    # Combined system prompt with context
    system_instruction = f"{CHAT_SYSTEM_PROMPT}\n\n=== MEETING CONTEXT ===\n{context}"

    # Map history to types.Content
    contents = []
    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        text = turn.get("content", "")
        if text:
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=text)]
                )
            )

    # Add new user message
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=message)]
        )
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
    )

    stream = await client.aio.models.generate_content_stream(
        model=MODEL,
        contents=contents,
        config=config,
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
