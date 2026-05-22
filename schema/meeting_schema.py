from pydantic import BaseModel
from typing import Optional


class MeetingSummary(BaseModel):
    key_discussion_points: list[str]
    decisions_made: list[str]
    concise_summary: str
    open_questions: list[str]
    missing_information: list[str]


class ActionItem(BaseModel):
    action: str
    owner: str          # "Unassigned" if not mentioned
    due_date: str       # "Needs date" if not mentioned
    status: str         # "Clear" | "Needs clarification"
    priority: str       # "High" | "Medium" | "Low"


class ActionItemReport(BaseModel):
    action_items: list[ActionItem]
    flagged_issues: list[str]


class MeetingWorkflowResult(BaseModel):
    summary: MeetingSummary
    action_report: ActionItemReport
