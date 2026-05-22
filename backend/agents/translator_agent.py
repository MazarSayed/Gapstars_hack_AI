from google import genai
from google.genai import types
from utils import DEFAULT_MODEL, load_prompt

_SYSTEM_PROMPT = load_prompt("translator_prompt")


async def translate_transcript(
    client: genai.Client,
    text: str,
    target_language: str,
) -> str:
    """Translates text into target_language. Returns the original text unchanged if target is English."""
    if target_language.strip().lower() == "english":
        return text

    response = await client.aio.models.generate_content(
        model=DEFAULT_MODEL,
        contents=f"Translate the following text into {target_language}:\n\n{text}",
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
    )
    return response.text.strip()
