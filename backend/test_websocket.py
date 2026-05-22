"""
WebSocket streaming test.
Connects to /ws/summarize, sends the sample transcript, and prints every event.
Run with:  python test_websocket.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=False), override=True)

from fastapi.testclient import TestClient
from main import app, SAMPLE_TRANSCRIPT


def test_ws_streaming():
    client = TestClient(app)

    summary_chunks = 0
    actions_chunks = 0
    summary_done = False
    actions_done = False

    print("\n" + "=" * 60)
    print("WebSocket Streaming Test")
    print("=" * 60)

    with client.websocket_connect("/ws/summarize") as ws:
        ws.send_json({"transcript": SAMPLE_TRANSCRIPT, "language": "English"})
        print("Sent transcript. Waiting for events...\n")

        while True:
            msg = ws.receive_json()
            event = msg["type"]

            if event == "status":
                print(f"[STATUS]  {msg['message']}")

            elif event == "summary_chunk":
                summary_chunks += 1
                preview = msg["chunk"].replace("\n", " ")[:60]
                print(f"[SUMMARY CHUNK #{summary_chunks:02d}]  {preview}")

            elif event == "actions_chunk":
                actions_chunks += 1
                preview = msg["chunk"].replace("\n", " ")[:60]
                print(f"[ACTIONS CHUNK #{actions_chunks:02d}]  {preview}")

            elif event == "summary_done":
                summary_done = True
                d = msg["data"]
                print(f"\n[SUMMARY DONE]")
                print(f"  concise_summary : {d.get('concise_summary', '')[:100]}")
                print(f"  key_points      : {len(d.get('key_discussion_points', []))} items")
                print(f"  decisions       : {len(d.get('decisions_made', []))} items")
                print(f"  open_questions  : {len(d.get('open_questions', []))} items\n")

            elif event == "actions_done":
                actions_done = True
                d = msg["data"]
                print(f"[ACTIONS DONE]")
                print(f"  action_items    : {len(d.get('action_items', []))} items")
                print(f"  flagged_issues  : {len(d.get('flagged_issues', []))} items\n")

            elif event == "complete":
                print("[COMPLETE]  Both agents finished.")
                break

            elif event == "error":
                print(f"[ERROR]  {msg['message']}")
                sys.exit(1)

            else:
                print(f"[EVENT: {event}]  {msg.keys()}")

    print("\n" + "=" * 60)
    print(f"Summary chunks   : {summary_chunks}")
    print(f"Actions chunks   : {actions_chunks}")
    print(f"Summary done     : {summary_done}")
    print(f"Actions done     : {actions_done}")
    print("=" * 60)

    assert summary_done, "summary_done event never received"
    assert actions_done, "actions_done event never received"
    assert summary_chunks > 0, "no summary chunks streamed"
    assert actions_chunks > 0, "no actions chunks streamed"
    print("\nAll assertions passed.")


if __name__ == "__main__":
    test_ws_streaming()
