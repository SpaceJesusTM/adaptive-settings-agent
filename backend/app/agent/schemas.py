"""Structured output contract for the local model.

The *generation* schema is deliberately lenient (no length limits) so that grammar-constrained decoding
in Ollama does not fail on long strings; server-side validation trims and checks everything afterwards.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DimensionLit = Literal[
    "performance", "input_latency", "visibility", "visual_quality", "audio_awareness",
    "communication", "focus", "comfort", "network_stability",
]
FactKeyLit = Literal[
    "mouse_sensitivity",
    "push_to_talk_key",
    "voice_activation",
    "ping_key",
    "crouch_walk_convention",
    "crosshair_style",
]


class DraftRecommendation(BaseModel):
    setting_id: str = Field(description="Exact setting id from the SETTINGS list, e.g. 'val.video.bloom'.")
    proposed_value: str = Field(description="One allowed option label exactly as listed, or a number inside the range.")
    why_for_goal: str = Field(description="Why this may help the user's goal. Conditional, no invented numbers.")
    tradeoff_note: Optional[str] = Field(default=None, description="Main downside or uncertainty, if any.")
    confidence: Literal["low", "medium", "high"]
    goal_dimension: Optional[DimensionLit] = None
    based_on: Optional[str] = Field(default=None, description="Which user goal or saved preference this is based on.")


class DraftExplanation(BaseModel):
    setting_id: str
    explanation: str = Field(description="Plain-language explanation grounded in the catalogue description.")


class DraftPreference(BaseModel):
    dimension: DimensionLit
    direction: Literal["prioritize", "deprioritize"]
    scope: Literal["session", "durable"]
    user_quote: str = Field(description="The user's words that express this preference.")


class DraftMemoryAction(BaseModel):
    kind: Literal["preference", "fact"]
    dimension: Optional[DimensionLit] = None
    direction: Literal["prioritize", "deprioritize"] = "prioritize"
    fact_key: Optional[FactKeyLit] = None
    value_text: Optional[str] = None
    scope: Literal["session", "durable"] = "durable"
    game: Optional[Literal["valorant", "cs2"]] = None
    user_quote: str = Field(default="", description="Short verbatim quote expressing this explicit instruction.")


class AssistantDraft(BaseModel):
    intent: Literal["recommend", "explain", "navigate", "preference", "clarify", "other"]
    reply: str = Field(description="Short conversational answer in plain text (2-5 sentences).")
    goal_dimensions: list[DimensionLit] = Field(default_factory=list, description="The user's current goal as abstract dimensions.")
    goal_changed: bool = Field(default=False, description="True only when the user expresses or shifts an active session optimization goal.")
    knowns_and_unknowns: Optional[str] = Field(default=None, description="What you can and cannot know without measuring the user's PC.")
    recommendations: list[DraftRecommendation] = Field(default_factory=list)
    explanations: list[DraftExplanation] = Field(default_factory=list)
    navigate_to: Optional[str] = Field(default=None, description="Setting id to show the user, if they asked where something is.")
    preference_suggestions: list[DraftPreference] = Field(default_factory=list)
    explicit_memory_actions: list[DraftMemoryAction] = Field(
        default_factory=list,
        description="Unambiguous explicit memory/preference instructions requested by the user (empty on speculative/question turns).",
    )
    clarifying_question: Optional[str] = None


class BatchDraft(BaseModel):
    recommendations: list[DraftRecommendation] = Field(default_factory=list)
