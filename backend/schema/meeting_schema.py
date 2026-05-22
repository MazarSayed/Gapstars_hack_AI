from enum import Enum
from pydantic import BaseModel, Field


class ActionStatus(str, Enum):
    clear = "Clear"
    needs_clarification = "Needs clarification"


class ActionPriority(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"


class ActionItem(BaseModel):
    action: str = Field(..., description="Verb-led description of the task to be completed")
    owner: str = Field(default="Unassigned", description="Person responsible for the action")
    due_date: str = Field(default="Needs date", description="Target completion date or 'Needs date'")
    status: ActionStatus = Field(default=ActionStatus.clear)
    priority: ActionPriority = Field(default=ActionPriority.medium)


class ActionItemReport(BaseModel):
    action_items: list[ActionItem] = Field(default_factory=list)
    flagged_issues: list[str] = Field(
        default_factory=list,
        description="Actions missing owner, due date, or needing clarification",
    )


class MeetingSummary(BaseModel):
    concise_summary: str = Field(..., description="2-4 sentence overview of the meeting")
    key_discussion_points: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(
        default_factory=list,
        description="Context referenced but not provided, or unclear details",
    )


class MeetingWorkflowResult(BaseModel):
    summary: MeetingSummary
    action_report: ActionItemReport
