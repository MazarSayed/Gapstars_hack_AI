from typing import AsyncGenerator
from google import genai
from google.genai import types
from utils import DEFAULT_MODEL, load_prompt, stream_text_chunks

_SYSTEM_PROMPT = load_prompt("project_chat_prompt")


def _format_action(a: dict) -> str:
    return f"{a.get('action')} (Owner: {a.get('owner')}, Due: {a.get('due_date')})"


def _build_context(meetings: list[dict]) -> str:
    parts = []
    for i, m in enumerate(meetings, 1):
        header = f"--- Meeting {i}: {m.get('name', 'Untitled')} ---"
        summary = m.get("summary", {})
        actions = m.get("actions", {})
        transcript_snippet = m.get("transcript", "")[:3000]
        action_items_str = "; ".join(_format_action(a) for a in actions.get("action_items", []))

        parts.append(
            f"{header}\n"
            f"Concise Summary: {summary.get('concise_summary', 'N/A')}\n"
            f"Decisions Made: {'; '.join(summary.get('decisions_made', []))}\n"
            f"Open Questions: {'; '.join(summary.get('open_questions', []))}\n"
            f"Action Items: {action_items_str}\n"
            f"Transcript Excerpt:\n{transcript_snippet}\n"
        )
    return "\n".join(parts)


async def stream_project_chat(
    client: genai.Client,
    question: str,
    meetings: list[dict],
    history: list[dict],
) -> AsyncGenerator[str, None]:
    """Stream an answer to a project-scoped question using all meeting data."""
    context = _build_context(meetings)

    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["text"])]))

    user_turn = (
        f"Project Meeting Data:\n{context}\n\n"
        f"Question: {question}"
        if not history
        else question
    )
    contents.append(types.Content(role="user", parts=[types.Part(text=user_turn)]))

    config = types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT)
    stream = await client.aio.models.generate_content_stream(
        model=DEFAULT_MODEL,
        contents=contents,
        config=config,
    )
    async for chunk in stream_text_chunks(stream):
        yield chunk
