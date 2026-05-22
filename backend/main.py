import asyncio
import json
import os
from dotenv import load_dotenv
from google import genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.meeting_summarizer import stream_meeting_summarizer
from agents.action_item_agent import stream_action_item_agent
from agents.followup_agent import stream_followup_agent
from agents.translator_agent import translate_transcript
from agents.chat_agent import stream_chat_agent


SAMPLE_TRANSCRIPT = """
Meeting: Q2 Product Planning
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

Sarah: I don't have that info yet — I'll check with finance and get back to everyone.
"""

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

load_dotenv()
app = FastAPI(title="Meeting Workflow API")


def _make_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


@app.websocket("/ws/summarize")
async def ws_summarize(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        transcript = data.get("transcript", SAMPLE_TRANSCRIPT)
        language = data.get("language", "English")

        client = _make_client()

        if language.strip().lower() != "english":
            await websocket.send_json({"type": "status", "message": f"Translating to {language}..."})
            transcript = await translate_transcript(client, transcript, language)

        await websocket.send_json({"type": "status", "message": "Agents started"})

        # Lock prevents concurrent writes to the WebSocket from two tasks
        send_lock = asyncio.Lock()

        async def send(payload: dict) -> None:
            async with send_lock:
                await websocket.send_json(payload)

        async def run_and_stream(stream_fn, agent_type: str, *args) -> dict:
            accumulated = ""
            async for chunk in stream_fn(client, *args):
                accumulated += chunk
                await send({"type": f"{agent_type}_chunk", "chunk": chunk})
            result = _parse_json(accumulated)
            await send({"type": f"{agent_type}_done", "data": result})
            return result

        summary_data, actions_data = await asyncio.gather(
            run_and_stream(stream_meeting_summarizer, "summary", transcript),
            run_and_stream(stream_action_item_agent, "actions", transcript),
        )

        await send({"type": "status", "message": "Drafting follow-up email and Jira tasks..."})
        await run_and_stream(stream_followup_agent, "followup", summary_data, actions_data)

        await websocket.send_json({"type": "complete"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    chat_history = []
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            transcript = data.get("transcript", "")
            analysis_results = data.get("analysis_results", None)

            if not user_message.strip():
                continue

            client = _make_client()
            accumulated_response = ""

            async for chunk in stream_chat_agent(
                client=client,
                message=user_message,
                history=chat_history,
                transcript=transcript,
                analysis_results=analysis_results,
            ):
                accumulated_response += chunk
                await websocket.send_json({"type": "chunk", "chunk": chunk})

            await websocket.send_json({"type": "done", "response": accumulated_response})

            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "model", "content": accumulated_response})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
