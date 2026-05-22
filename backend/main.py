import asyncio
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.meeting_summarizer import stream_meeting_summarizer
from agents.action_item_agent import stream_action_item_agent
from agents.followup_agent import stream_followup_agent
from agents.translator_agent import translate_transcript
from agents.project_chat_agent import stream_project_chat
from agents.project_summary_agent import stream_project_summary
from agents.chat_agent import stream_chat_agent
from utils import get_langfuse, make_client, parse_json, propagate_attributes
from utils.file_processor import extract_transcript
import db


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

app = FastAPI(title="Meeting Workflow API")


@app.on_event("startup")
async def startup():
    await db.init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str


@app.post("/project")
async def create_project(body: CreateProjectRequest):
    return await db.create_project(body.name)


@app.get("/project")
async def list_projects():
    return await db.list_projects()


@app.get("/project/{project_id}")
async def get_project_detail(project_id: str):
    project = await db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "project_id": project["project_id"],
        "name": project["name"],
        "meetings": [
            {
                "id": m["id"],
                "name": m["name"],
                "summary": m["summary"],
                "actions": m["actions"],
                "followup": m.get("followup", {})
            }
            for m in project["meetings"]
        ],
    }


@app.post("/project/{project_id}/meeting")
async def add_meeting_to_project(project_id: str, file: UploadFile = File(...)):
    project = await db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    data = await file.read()
    content_type = file.content_type or ""
    client = make_client()

    try:
        transcript = await extract_transcript(client, file.filename or "", content_type, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def collect(stream_fn, *args) -> dict:
        accumulated = ""
        async for chunk in stream_fn(client, *args):
            accumulated += chunk
        return parse_json(accumulated)

    with propagate_attributes(metadata={"project_id": project_id, "filename": file.filename}):
        with get_langfuse().start_as_current_observation(
            as_type="span",
            name="meeting-upload",
            input={"project_id": project_id, "filename": file.filename},
        ) as root:
            summary_data, actions_data = await asyncio.gather(
                collect(stream_meeting_summarizer, transcript),
                collect(stream_action_item_agent, transcript),
            )
            # Draft followup email and Jira tasks using stream_followup_agent
            followup_data = await collect(stream_followup_agent, summary_data, actions_data)
            root.update(output={"meetings_analyzed": 1})

    await db.add_meeting(project_id, file.filename or "", transcript, summary_data, actions_data, followup_data)
    total = await db.meeting_count(project_id)

    # Regenerate project summary in the background so the next GET is fresh
    asyncio.create_task(_refresh_project_summary(project_id))

    return {
        "meeting_name": file.filename,
        "summary": summary_data,
        "actions": actions_data,
        "followup": followup_data,
        "total_meetings": total,
    }


@app.post("/project/{project_id}/meeting/{meeting_id}/followup")
async def generate_meeting_followup(project_id: str, meeting_id: int):
    project = await db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    meeting = await db.get_meeting(project_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    client = make_client()
    summary_data = meeting["summary"]
    actions_data = meeting["actions"]

    async def collect(stream_fn, *args) -> dict:
        accumulated = ""
        async for chunk in stream_fn(client, *args):
            accumulated += chunk
        return parse_json(accumulated)

    try:
        followup_data = await collect(stream_followup_agent, summary_data, actions_data)
        await db.save_meeting_followup(project_id, meeting_id, followup_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate followup: {str(e)}")

    return {"followup": followup_data}


async def _refresh_project_summary(project_id: str) -> None:
    try:
        project = await db.get_project(project_id)
        if not project or not project["meetings"]:
            return
        client = make_client()
        with propagate_attributes(metadata={"project_id": project_id}):
            with get_langfuse().start_as_current_observation(as_type="span", name="project-summary-refresh"):
                accumulated = ""
                async for chunk in stream_project_summary(client, project["meetings"]):
                    accumulated += chunk
                summary = parse_json(accumulated)
        summary["meetings_analyzed"] = len(project["meetings"])
        await db.save_project_summary(project_id, summary)
    except Exception:
        pass  # summary is best-effort; don't fail the meeting upload


@app.get("/project/{project_id}/summary")
async def get_project_summary(project_id: str, refresh: bool = False):
    project = await db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project["meetings"]:
        raise HTTPException(status_code=422, detail="No meetings in this project yet")

    if refresh or (cached := await db.get_project_summary(project_id)) is None:
        client = make_client()
        accumulated = ""
        async for chunk in stream_project_summary(client, project["meetings"]):
            accumulated += chunk
        cached = parse_json(accumulated)
        cached["meetings_analyzed"] = len(project["meetings"])
        await db.save_project_summary(project_id, cached)

    return cached


@app.websocket("/ws/project/{project_id}/chat")
async def ws_project_chat(websocket: WebSocket, project_id: str):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    try:
        project = await db.get_project(project_id)
        if project is None:
            await websocket.send_json({"type": "error", "message": "Project not found"})
            await websocket.close()
            return

        client = make_client()
        history: list[dict] = []

        await websocket.send_json({"type": "ready"})

        while True:
            data = await websocket.receive_json()
            question = data.get("question", "").strip()
            if not question:
                continue

            history.append({"role": "user", "text": question})
            answer = ""

            with propagate_attributes(session_id=session_id, metadata={"project_id": project_id}):
                with get_langfuse().start_as_current_observation(
                    as_type="span",
                    name="project-chat-turn",
                    input={"question": question, "history_turns": len(history) - 1},
                ) as root:
                    async for chunk in stream_project_chat(client, question, project["meetings"], history[:-1]):
                        answer += chunk
                        await websocket.send_json({"type": "chunk", "chunk": chunk})
                    root.update(output={"answer_chars": len(answer)})

            history.append({"role": "assistant", "text": answer})
            await websocket.send_json({"type": "done"})

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


@app.post("/upload/transcript")
async def upload_transcript(file: UploadFile = File(...)):
    """
    Upload a DOCX, PDF, audio, or video file and receive the extracted transcript text.
    The returned transcript can be passed directly to the /ws/summarize WebSocket.
    """
    data = await file.read()
    content_type = file.content_type or ""
    try:
        client = make_client()
        transcript = await extract_transcript(client, file.filename or "", content_type, data)
        return {"transcript": transcript, "filename": file.filename}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/summarize")
async def ws_summarize(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    try:
        data = await websocket.receive_json()
        transcript = data.get("transcript", SAMPLE_TRANSCRIPT)
        language = data.get("language", "English")

        client = make_client()

        with propagate_attributes(session_id=session_id):
            with get_langfuse().start_as_current_observation(
                as_type="span",
                name="meeting-analysis",
                input={"language": language, "transcript_chars": len(transcript)},
            ) as root:
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
                    result = parse_json(accumulated)
                    await send({"type": f"{agent_type}_done", "data": result})
                    return result

                summary_data, actions_data = await asyncio.gather(
                    run_and_stream(stream_meeting_summarizer, "summary", transcript),
                    run_and_stream(stream_action_item_agent, "actions", transcript),
                )

                await send({"type": "status", "message": "Drafting follow-up email and Jira tasks..."})
                followup_data = await run_and_stream(stream_followup_agent, "followup", summary_data, actions_data)

                root.update(output={"action_count": len(actions_data.get("action_items", []))})

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

            client = make_client()
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
