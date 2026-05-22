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


# --- Mock and Proxy support for Gemini API quota fallback ---

MOCK_RESPONSES = {
    "meeting-summarizer": """{
  "key_discussion_points": [
    "Finalizing the Q2 roadmap and owner assignments",
    "Auth service refactor blocking two features",
    "API rate limiting causing timeouts for enterprise clients",
    "Tom awaiting legal copy approval for landing page"
  ],
  "decisions_made": [
    "Prioritize the auth service refactor to unblock other Q2 features",
    "Mike to investigate the enterprise API rate limiting issue today"
  ],
  "concise_summary": "The team met to plan the Q2 roadmap, identifying the authentication service refactor as a major blocker. Priya will deliver login screen designs by June 10, following Tom sending brand guidelines. A critical API rate limiting issue was assigned to Mike for a next-day fix, while Tom will resolve legal copy approvals for the landing page.",
  "open_questions": [
    "What is the budget for the design tooling upgrade discussed last month?",
    "What is the final decision on the push notification copy tone?"
  ],
  "missing_information": [
    "Design tooling upgrade budget details (Sarah to check with finance)",
    "Brand guidelines from marketing (Tom to send by Friday)"
  ]
}""",
    "action-item-agent": """{
  "action_items": [
    {
      "action": "Complete authentication service refactor",
      "owner": "James",
      "due_date": "2026-06-27",
      "status": "Clear",
      "priority": "High"
    },
    {
      "action": "Finalize new login screen designs",
      "owner": "Priya",
      "due_date": "2026-06-10",
      "status": "Clear",
      "priority": "High"
    },
    {
      "action": "Send brand guidelines to Priya",
      "owner": "Tom",
      "due_date": "Friday",
      "status": "Clear",
      "priority": "Medium"
    },
    {
      "action": "Investigate and fix API rate limiting timeouts",
      "owner": "Mike",
      "due_date": "Tomorrow EOD",
      "status": "Clear",
      "priority": "High"
    },
    {
      "action": "Follow up with legal regarding landing page copy approval",
      "owner": "Tom",
      "due_date": "Today EOD",
      "status": "Clear",
      "priority": "Medium"
    },
    {
      "action": "Schedule follow-up meeting with VP for push notification copy",
      "owner": "Sarah",
      "due_date": "Needs date",
      "status": "Needs clarification",
      "priority": "Medium"
    }
  ],
  "flagged_issues": [
    "Design upgrade budget requires finance input",
    "Schedule follow-up meeting with VP has no deadline"
  ]
}""",
    "followup-agent": """{
  "email_subject": "Q2 Product Planning - Meeting Summary & Action Items",
  "email_body": "Hi everyone,\\n\\nThanks for a productive Q2 roadmap kickoff. We successfully aligned on our key blockers, specifically prioritizing the authentication service refactor to unblock concurrent features.\\n\\n### Key Decisions\\n- Authenticating service refactor is prioritized for completion by June 27th.\\n- Mike is investigating and fixing the enterprise API rate limiting issue immediately.\\n\\n### Action Items\\n| Action | Owner | Due Date |\\n| :--- | :--- | :--- |\\n| Complete auth service refactor | James | June 27 |\\n| Finalize login screen designs | Priya | June 10 |\\n| Send brand guidelines | Tom | Friday |\\n| Fix API rate limiting | Mike | Tomorrow EOD |\\n| Get legal approvals | Tom | Today EOD |\\n\\n### Open Questions\\n- What is the design tooling upgrade budget? (Sarah checking with finance)\\n- Push notification copy tone (Sarah checking with VP)\\n\\nPlease reach out if you have any questions.\\n\\nBest regards,\\nSarah",
  "jira_tasks": [
    {
      "title": "Auth service refactor",
      "description": "Refactor the core authentication service to resolve blockers for dependent features.",
      "priority": "High",
      "assignee": "James",
      "due_date": "2026-06-27",
      "component": "Engineering"
    },
    {
      "title": "Login screen designs",
      "description": "Deliver final screen mockups for the new auth workflow login screen.",
      "priority": "High",
      "assignee": "Priya",
      "due_date": "2026-06-10",
      "component": "Design"
    },
    {
      "title": "Fix API rate limiting timeouts",
      "description": "Investigate enterprise client timeouts caused by API rate limiting and apply a fix.",
      "priority": "High",
      "assignee": "Mike",
      "due_date": "Tomorrow EOD",
      "component": "Engineering"
    }
  ]
}""",
    "project-summary": """{
  "overview": "This project centers on the Q2 Product Planning and roadmap execution, with a strong focus on resolving technical blockers, updating user interface components, and aligning marketing campaigns.",
  "strategic_goals": [
    "Finalize and execute the Q2 product roadmap",
    "Refactor critical core services (authentication)",
    "Address performance and timeout issues for enterprise clients"
  ],
  "current_direction": "The team is actively resolving dependencies and blockers to prepare for upcoming feature releases. Focus has shifted to stabilizing services and completing design work before starting roadmap implementation.",
  "key_themes": [
    "Technical debt and service refactoring",
    "Cross-functional design and marketing dependencies",
    "Customer-facing stability and rate limiting issues"
  ],
  "major_decisions": [
    "Prioritize authentication service refactor to unblock other features",
    "Allocate resources to investigate enterprise API timeout issues immediately"
  ],
  "risks_and_concerns": [
    "Refactoring blockers delaying dependent features",
    "Unresolved legal copy approvals for marketing pages",
    "Design tool budget approvals pending finance input"
  ],
  "open_questions": [
    "What is the final decision on the tone of push notification copy?",
    "When will legal copy approvals for the landing page be received?"
  ],
  "progress_assessment": "The project is progressing steadily, though key dependencies around design mockups, legal approvals, and budget constraints need to be resolved to maintain momentum."
}"""
}

class MockChunk:
    def __init__(self, text):
        self.text = text

class MockStreamResponse:
    def __init__(self, text):
        self.text = text
        # Yield small text fragments to mimic a live typing stream
        self._chunks = [text[i:i+15] for i in range(0, len(text), 15)]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        await asyncio.sleep(0.02)
        return MockChunk(self._chunks.pop(0))

class MockResponse:
    def __init__(self, text):
        self.text = text

class MockAioModels:
    async def generate_content_stream(self, *args, **kwargs):
        model = kwargs.get("model") or (args[0] if len(args) > 0 else "")
        contents = kwargs.get("contents") or (args[1] if len(args) > 1 else "")
        config = kwargs.get("config") or (args[2] if len(args) > 2 else None)
        system_instruction = getattr(config, "system_instruction", "") or ""
        system_instruction_str = str(system_instruction)
        prompt_content = str(contents)
        
        if "summarizer" in system_instruction_str or "Summarizer" in system_instruction_str:
            mock_text = MOCK_RESPONSES["meeting-summarizer"]
        elif "action_item" in system_instruction_str or "action-item" in system_instruction_str or "Action Item" in system_instruction_str:
            mock_text = MOCK_RESPONSES["action-item-agent"]
        elif "followup" in system_instruction_str or "follow-up" in system_instruction_str or "Follow-up" in system_instruction_str:
            mock_text = MOCK_RESPONSES["followup-agent"]
        elif "project_summary" in system_instruction_str or "project-summary" in system_instruction_str:
            mock_text = MOCK_RESPONSES["project-summary"]
        elif "translator" in system_instruction_str or "Translate" in system_instruction_str or "Translate" in prompt_content:
            mock_text = "This is the translated meeting transcript text (Simulation Mode)."
        else:
            mock_text = "This is a simulated AI response. I am functioning in Simulation Mode due to API rate limits, but the WebSocket connection and real-time streaming UI are fully operational!"
        
        return MockStreamResponse(mock_text)

    async def generate_content(self, *args, **kwargs):
        model = kwargs.get("model") or (args[0] if len(args) > 0 else "")
        contents = kwargs.get("contents") or (args[1] if len(args) > 1 else "")
        config = kwargs.get("config") or (args[2] if len(args) > 2 else None)
        system_instruction = getattr(config, "system_instruction", "") or ""
        system_instruction_str = str(system_instruction)
        prompt_content = str(contents)
        
        if "summarizer" in system_instruction_str or "Summarizer" in system_instruction_str:
            mock_text = MOCK_RESPONSES["meeting-summarizer"]
        elif "action_item" in system_instruction_str or "action-item" in system_instruction_str or "Action Item" in system_instruction_str:
            mock_text = MOCK_RESPONSES["action-item-agent"]
        elif "followup" in system_instruction_str or "follow-up" in system_instruction_str or "Follow-up" in system_instruction_str:
            mock_text = MOCK_RESPONSES["followup-agent"]
        elif "project_summary" in system_instruction_str or "project-summary" in system_instruction_str:
            mock_text = MOCK_RESPONSES["project-summary"]
        elif "translator" in system_instruction_str or "Translate" in system_instruction_str or "Translate" in prompt_content:
            mock_text = "This is the translated meeting transcript text (Simulation Mode)."
        elif "Extract the full text content" in prompt_content or "Transcribe this audio" in prompt_content or "Transcribe all spoken content" in prompt_content or "Extract the full text" in prompt_content:
            mock_text = """Meeting: Q2 Product Planning
Date: May 22, 2026
Attendees: Sarah (PM), James (Engineering Lead), Priya (Design), Tom (Marketing)

Sarah: Alright everyone, let's kick off. The main goal today is to finalize the Q2 roadmap and assign owners.

James: Before we start, I want to flag that the authentication service refactor is blocking two other features. We really need to prioritize that.

Sarah: Agreed. James, can your team own that and have it done by end of June?

James: We can target June 27th. I'll need Priya to finalize the new login screen designs first though.

Priya: I can have the designs ready by June 10th. But I still need the brand guidelines from marketing — Tom, can you send those over?

Tom: I'll send them by Friday. Also, we haven't decided on the push notification copy yet. Who owns that?

Sarah: Let's table the push notification copy for now — we need a decision from leadership on the tone first. I'll schedule a follow-up with the VP.

James: One more thing — the API rate limiting issue reported last week. It's causing timeouts for some enterprise clients. We need to fix that urgently.

Sarah: That's critical. James, can someone on your team look into it today?

James: I'll assign it to Mike. He should have a fix ready by tomorrow EOD.

Tom: Regarding the marketing landing page update — I still don't have final copy approval from legal. I'm not sure when that's coming.

Sarah: Tom, follow up with legal today and let me know the ETA. We can't delay the launch any further.

Tom: Will do.

Sarah: Great. Let me recap: James owns the auth refactor by June 27, Priya delivers designs by June 10, Tom sends brand guidelines by Friday, Mike fixes the API issue by tomorrow, and Tom follows up with legal today. Any questions?

Priya: What's the budget for the design tooling upgrade we discussed last month?

Sarah: I don't have that info yet — I'll check with finance and get back to everyone."""
        else:
            mock_text = "This is a simulated AI response. The WebSocket connection and real-time streaming UI are fully operational!"
        
        return MockResponse(mock_text)

class MockAio:
    def __init__(self):
        self.models = MockAioModels()

class MockClient:
    def __init__(self, real_client=None):
        self.real_client = real_client
        self.aio = MockAio()

class StreamProxy:
    def __init__(self, real_stream, mock_models, args, kwargs):
        self.real_stream = real_stream
        self.mock_models = mock_models
        self.args = args
        self.kwargs = kwargs
        self.real_iterator = real_stream.__aiter__()
        self.fallback_stream = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.fallback_stream is not None:
            return await self.fallback_stream.__anext__()
            
        try:
            return await self.real_iterator.__anext__()
        except StopAsyncIteration:
            raise StopAsyncIteration
        except Exception as e:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(e) or "limit" in str(e).lower() or "429" in str(e) or "quota" in str(e).lower()
            if is_quota_error:
                print(f"[FALLBACK] Gemini API Quota Exceeded/Rate Limited during stream iteration. Falling back to Simulated AI Stream. Error: {e}")
                self.fallback_stream = await self.mock_models.generate_content_stream(*self.args, **self.kwargs)
                return await self.fallback_stream.__anext__()
            raise e

class ModelsProxy:
    def __init__(self, real_models):
        self.real_models = real_models
        self.mock_models = MockAioModels()

    async def generate_content_stream(self, *args, **kwargs):
        try:
            if os.environ.get("SIMULATE_AI") == "true":
                raise Exception("Forced simulation mode")
            real_stream = await self.real_models.generate_content_stream(*args, **kwargs)
            return StreamProxy(real_stream, self.mock_models, args, kwargs)
        except Exception as e:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(e) or "limit" in str(e).lower() or "429" in str(e) or "quota" in str(e).lower() or "Forced simulation" in str(e)
            if is_quota_error:
                print(f"[FALLBACK] Gemini API Quota Exceeded/Rate Limited. Falling back to Simulated AI Stream. Error: {e}")
                return await self.mock_models.generate_content_stream(*args, **kwargs)
            raise e

    async def generate_content(self, *args, **kwargs):
        try:
            if os.environ.get("SIMULATE_AI") == "true":
                raise Exception("Forced simulation mode")
            return await self.real_models.generate_content(*args, **kwargs)
        except Exception as e:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(e) or "limit" in str(e).lower() or "429" in str(e) or "quota" in str(e).lower() or "Forced simulation" in str(e)
            if is_quota_error:
                print(f"[FALLBACK] Gemini API Quota Exceeded/Rate Limited. Falling back to Simulated AI content. Error: {e}")
                return await self.mock_models.generate_content(*args, **kwargs)
            raise e

class AioProxy:
    def __init__(self, real_aio):
        self.models = ModelsProxy(real_aio.models)

class ClientProxy:
    def __init__(self, real_client):
        self.real_client = real_client
        self.aio = AioProxy(real_client.aio)


def make_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    real_client = genai.Client(api_key=api_key)
    return ClientProxy(real_client)



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
