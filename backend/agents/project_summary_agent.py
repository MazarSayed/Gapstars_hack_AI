from typing import AsyncGenerator
from google import genai
from utils import DEFAULT_MODEL, load_prompt, make_json_config, traced_stream_chunks

_CONFIG = make_json_config(load_prompt("project_summary_prompt"))


def _build_transcript_bundle(meetings: list[dict]) -> str:
    parts = []
    for i, m in enumerate(meetings, 1):
        name = m.get("name") or f"Meeting {i}"
        transcript = (m.get("transcript") or "").strip()
        if transcript:
            parts.append(f"=== Meeting {i}: {name} ===\n{transcript}")
    return "\n\n".join(parts)


async def stream_project_summary(
    client: genai.Client,
    meetings: list[dict],
) -> AsyncGenerator[str, None]:
    """Stream a strategic project summary synthesized from all meeting transcripts."""
    bundle = _build_transcript_bundle(meetings)
    contents = (
        f"The following are all meeting transcripts for this project, in chronological order "
        f"(most recent last). Synthesize a strategic project summary from them.\n\n{bundle}"
    )
    async for chunk in traced_stream_chunks(
        client, model=DEFAULT_MODEL, contents=contents, config=_CONFIG, name="project-summary"
    ):
        yield chunk
