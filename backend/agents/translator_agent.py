from google import genai
from google.genai import types
from utils import DEFAULT_MODEL, load_prompt, traced_generate

_SYSTEM_PROMPT = load_prompt("translator_prompt")
_CONFIG = types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT)


async def translate_transcript(
    client: genai.Client,
    text: str,
    target_language: str,
) -> str:
    """Translates text into target_language. Returns the original text unchanged if target is English."""
    if target_language.strip().lower() == "english":
        return text

    contents = f"Translate the following text into {target_language}:\n\n{text}"
    return await traced_generate(
        client, model=DEFAULT_MODEL, contents=contents, config=_CONFIG, name="translator"
    )
