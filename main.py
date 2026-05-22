"""
Meeting Summary & Action Workflow
Epic 8 — two agents running in parallel:
  Agent 1: Meeting Summarizer  →  key points, decisions, summary, open questions
  Agent 2: Action Item Agent   →  action items, owners, due dates, flags
  Translator Agent             →  optional pre-translation to target language
"""

import asyncio
import json
import os
from google import genai

from agents.meeting_summarizer import run_meeting_summarizer
from agents.action_item_agent import run_action_item_agent
from agents.translator_agent import translate_transcript
from schema.meeting_schema import MeetingWorkflowResult


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


def print_results(result: MeetingWorkflowResult) -> None:
    print("\n" + "=" * 60)
    print("MEETING SUMMARY (Agent 1)")
    print("=" * 60)

    s = result.summary
    print("\nConcise Summary:")
    print(f"  {s.concise_summary}")

    print("\nKey Discussion Points:")
    for point in s.key_discussion_points:
        print(f"  • {point}")

    print("\nDecisions Made:")
    for decision in s.decisions_made:
        print(f"  ✓ {decision}")

    print("\nOpen Questions:")
    for q in s.open_questions:
        print(f"  ? {q}")

    print("\nMissing Information:")
    for m in s.missing_information:
        print(f"  ⚠ {m}")

    print("\n" + "=" * 60)
    print("ACTION ITEMS (Agent 2)")
    print("=" * 60)

    for i, item in enumerate(result.action_report.action_items, 1):
        status_icon = "✓" if item.status == "Clear" else "⚠"
        print(f"\n{i}. [{item.priority}] {item.action}")
        print(f"   Owner: {item.owner}  |  Due: {item.due_date}  |  {status_icon} {item.status}")

    if result.action_report.flagged_issues:
        print("\nFlagged Issues:")
        for issue in result.action_report.flagged_issues:
            print(f"  ⚑ {issue}")

    print("\n" + "=" * 60)


async def run_workflow(transcript: str, language: str = "English") -> MeetingWorkflowResult:
    """Translate (if needed) then run both agents in parallel."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    if language.strip().lower() != "english":
        print(f"Translating transcript to {language}...")
        transcript = await translate_transcript(client, transcript, language)

    print("Running Agent 1 (Meeting Summarizer) and Agent 2 (Action Item Agent) in parallel...")

    summary, action_report = await asyncio.gather(
        run_meeting_summarizer(client, transcript),
        run_action_item_agent(client, transcript),
    )

    return MeetingWorkflowResult(summary=summary, action_report=action_report)


async def main() -> None:
    result = await run_workflow(SAMPLE_TRANSCRIPT, language="English")
    print_results(result)

    with open("output.json", "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    print("\nFull output saved to output.json")


if __name__ == "__main__":
    asyncio.run(main())
