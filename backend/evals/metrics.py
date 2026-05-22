from dataclasses import dataclass
from enum import Enum


class Target(str, Enum):
    summary = "summary"
    action_report = "action_report"


@dataclass
class Metric:
    name: str
    description: str
    target: Target
    rubric: dict[int, str]

    def rubric_text(self) -> str:
        return "\n".join(
            f"  {score}: {desc}" for score, desc in sorted(self.rubric.items())
        )


METRICS: list[Metric] = [
    # ── Summary metrics ────────────────────────────────────────────────────
    Metric(
        name="summary_coverage",
        description=(
            "Fraction of the golden eval's key_discussion_points that are "
            "present in the actual output."
        ),
        target=Target.summary,
        rubric={
            1: "Fewer than half the key discussion points are present; major topics missing.",
            2: "About half the key points present; several important topics absent.",
            3: "Most key points covered but 2–3 notable omissions.",
            4: "Nearly all key points covered; at most 1 minor omission.",
            5: "All key discussion points fully captured.",
        },
    ),
    Metric(
        name="factual_accuracy",
        description=(
            "Correctness of every stated fact — numbers, names, decisions, "
            "quoted figures — relative to the golden eval. No hallucinations."
        ),
        target=Target.summary,
        rubric={
            1: "Multiple incorrect facts or significant contradictions with the golden eval.",
            2: "Some factual errors that could meaningfully mislead a reader.",
            3: "Mostly accurate with 1–2 minor inaccuracies or mis-stated details.",
            4: "Accurate; only trivial wording differences from the golden.",
            5: "Fully accurate; no contradictions, fabrications, or wrong figures.",
        },
    ),
    Metric(
        name="decision_completeness",
        description=(
            "How completely the actual output captures the decisions_made "
            "listed in the golden eval."
        ),
        target=Target.summary,
        rubric={
            1: "Fewer than half the golden decisions are present.",
            2: "About half the decisions captured; key decisions missing.",
            3: "Most decisions present; 1–2 notable gaps.",
            4: "All major decisions captured; minor phrasing differences only.",
            5: "All decisions from the golden eval are present and accurately described.",
        },
    ),
    Metric(
        name="concise_summary_quality",
        description=(
            "Whether the concise_summary is appropriately brief, accurate, "
            "and captures the meeting's essence as well as the golden eval does."
        ),
        target=Target.summary,
        rubric={
            1: "Inaccurate, far too long, or misses the main purpose of the meeting.",
            2: "Vague or omits major themes present in the golden summary.",
            3: "Covers the main points but noticeably over- or under-detailed.",
            4: "Clear and accurate; minor differences in emphasis or detail.",
            5: "Concise, accurate, and captures the meeting essence equivalently to the golden.",
        },
    ),
    Metric(
        name="open_questions_quality",
        description=(
            "How well the actual output identifies the unresolved topics and "
            "open questions present in the golden eval."
        ),
        target=Target.summary,
        rubric={
            1: "Misses most open questions or lists already-resolved topics as open.",
            2: "Captures some open questions but with significant gaps or errors.",
            3: "Most open questions present; 1–2 missed or mischaracterised.",
            4: "Nearly all open questions captured; minor phrasing differences.",
            5: "All open questions correctly identified and described.",
        },
    ),
    # ── Action-report metrics ───────────────────────────────────────────────
    Metric(
        name="action_completeness",
        description=(
            "How many of the golden eval's action items appear in the actual output."
        ),
        target=Target.action_report,
        rubric={
            1: "Fewer than half the golden action items are present.",
            2: "About half the action items captured; important actions missing.",
            3: "Most actions present; 2–3 missing or unrecognisably paraphrased.",
            4: "Nearly all actions present; at most 1 minor omission.",
            5: "All golden action items captured.",
        },
    ),
    Metric(
        name="owner_attribution_accuracy",
        description=(
            "How correctly owners are assigned to action items compared to the "
            "golden eval."
        ),
        target=Target.action_report,
        rubric={
            1: "Most owners wrong or missing where the golden has clear owners.",
            2: "Several owner mis-attributions or omissions.",
            3: "Most owners correct; 1–2 wrong or missing.",
            4: "Nearly all owners correct; trivial name-format differences only.",
            5: "All owners correctly attributed as in the golden eval.",
        },
    ),
    Metric(
        name="priority_calibration",
        description=(
            "Whether High / Medium / Low priorities match the golden eval's "
            "relative importance ranking across all action items."
        ),
        target=Target.action_report,
        rubric={
            1: "Priority assignments are largely inverted or arbitrary.",
            2: "Several actions significantly mis-prioritised (e.g. Low instead of High).",
            3: "Most priorities correct; 1–2 notable mismatches.",
            4: "Priorities aligned with golden; minor differences on borderline cases.",
            5: "Priority assignments fully consistent with the golden eval.",
        },
    ),
    Metric(
        name="flagged_issues_quality",
        description=(
            "Whether the flagged_issues identify the same process gaps, missing "
            "owners/dates, and ambiguities as the golden eval."
        ),
        target=Target.action_report,
        rubric={
            1: "No meaningful flags, or flags completely unrelated to the golden.",
            2: "Some relevant flags but major issues from the golden are missed.",
            3: "Most golden flags represented; 1–2 gaps or spurious additions.",
            4: "Nearly all flags aligned with golden; minor phrasing differences.",
            5: "Flagged issues fully match the golden eval's identified concerns.",
        },
    ),
]

SUMMARY_METRICS = [m for m in METRICS if m.target == Target.summary]
ACTION_METRICS = [m for m in METRICS if m.target == Target.action_report]
MAX_SCORE = 5
MAX_TOTAL = len(METRICS) * MAX_SCORE
