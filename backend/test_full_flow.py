"""
End-to-end flow test mimicking the frontend upload.
1. Upload a text file to POST /upload/transcript
2. Establish a WebSocket connection to /ws/summarize and stream results.
"""

import sys
import os
import json
import asyncio
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app

def test_full_flow():
    client = TestClient(app)
    
    # 1. Test transcript extraction REST endpoint
    print("Testing POST /upload/transcript...")
    file_content = b"Sarah: Hello Priya, did you finish the login mockup?\nPriya: Yes, I sent it yesterday."
    files = {"file": ("test_meeting.txt", file_content, "text/plain")}
    
    response = client.post("/upload/transcript", files=files)
    assert response.status_code == 200, f"Upload failed: {response.text}"
    data = response.json()
    assert "transcript" in data
    assert "filename" in data
    print("Transcript extracted successfully:", data["transcript"][:100])
    
    # 2. Test WebSocket summarization stream
    print("\nTesting WebSocket /ws/summarize stream...")
    with client.websocket_connect("/ws/summarize") as ws:
        ws.send_json({
            "transcript": data["transcript"],
            "filename": data["filename"],
            "language": "English"
        })
        
        status_events = []
        summary_chunks = []
        action_chunks = []
        followup_chunks = []
        completed = False
        
        while True:
            try:
                msg = ws.receive_json()
                event_type = msg.get("type")
                if event_type == "status":
                    print(f"  [Status] {msg.get('message')}")
                    status_events.append(msg.get("message"))
                elif event_type == "summary_chunk":
                    summary_chunks.append(msg.get("chunk"))
                elif event_type == "actions_chunk":
                    action_chunks.append(msg.get("chunk"))
                elif event_type == "followup_chunk":
                    followup_chunks.append(msg.get("chunk"))
                elif event_type == "complete":
                    print("  [Complete] Meeting ID:", msg.get("meeting_id"))
                    completed = True
                    break
                elif event_type == "error":
                    print(f"  [Error] {msg.get('message')}")
                    break
            except Exception as e:
                print("Exception during websocket read:", e)
                break
                
        assert completed, "Websocket stream did not complete successfully"
        assert len(summary_chunks) > 0, "No summary chunks received"
        assert len(action_chunks) > 0, "No action chunks received"
        assert len(followup_chunks) > 0, "No followup chunks received"
        print("End-to-end upload and stream tests passed successfully!")

if __name__ == "__main__":
    test_full_flow()
