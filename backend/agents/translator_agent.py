from pathlib import Path
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "translator_prompt.md"
TRANSLATOR_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


async def translate_transcript(
    client: genai.Client,
    text: str,
    target_language: str,
) -> str:
    """Translates text into target_language. Returns the original text unchanged if target is English."""
    if target_language.strip().lower() == "english":
        return text

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=f"Translate the following text into {target_language}:\n\n{text}",
        config=types.GenerateContentConfig(
            system_instruction=TRANSLATOR_SYSTEM_PROMPT,
        ),
    )
    return response.text.strip()
