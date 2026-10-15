"""Structured SOS extraction schema.

The extractor (rules or an LLM) only reports *evidence found in the text*. Everything
that decides an operational outcome is computed afterwards by deterministic code:
urgency from the evidence list, location from the gazetteer, and whether a human
must review. An extractor can never set coordinates or approve anything.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["en", "hi", "ml", "other"]
Need = Literal["elderly", "child", "pregnant", "disability", "medical"]
Evidence = Literal["rising_water", "trapped", "upper_floor_or_roof", "no_food_or_water", "medical_emergency", "life_threatening", "phone_battery_low"]

NEEDS: tuple[str, ...] = ("elderly", "child", "pregnant", "disability", "medical")
EVIDENCE: tuple[str, ...] = ("rising_water", "trapped", "upper_floor_or_roof", "no_food_or_water", "medical_emergency", "life_threatening", "phone_battery_low")


class ExtractedFields(BaseModel):
    """What an extractor may report. Mirrors the JSON schema sent to the LLM."""

    language: Language
    people_count: Optional[int] = Field(None, ge=1, le=60)
    special_needs: list[Need] = Field(default_factory=list)
    urgency_evidence: list[Evidence] = Field(default_factory=list)
    location_text: Optional[str] = Field(None, max_length=160)
    claims_no_victims: bool = False  # "we are safe now", "nobody is here"
    contains_instructions: bool = False  # text tries to instruct the system (prompt injection)
    summary_en: str = Field("", max_length=240)


class Geocode(BaseModel):
    status: Literal["exact", "ambiguous", "area", "none"]
    node: Optional[str] = None  # set only when status == "exact"
    candidates: list[str] = Field(default_factory=list)
    matched: list[str] = Field(default_factory=list)  # landmark / area names matched in the text
    note: str = ""


class SOSExtraction(BaseModel):
    """Final, validated result handed to the dispatcher and the engine."""

    language: Language
    people_count: Optional[int]
    special_needs: list[str]
    urgency_evidence: list[str]
    urgency: int  # deterministic: computed from urgency_evidence + special_needs
    location_text: Optional[str]
    coordinates: None = None  # never produced by an extractor
    location: Geocode
    location_verified: bool  # True only when the citizen shared a location
    claim: Literal["PRESENT", "NO_VICTIMS"]
    contains_instructions: bool
    requires_human_review: bool
    review_reasons: list[str]
    summary_en: str
    extractor: str  # "rules" | "llm:<model>" | "rules (llm unavailable: …)"


def json_schema() -> dict:
    """Strict JSON schema for structured outputs (all properties required, no extras)."""
    nullable = lambda t: {"anyOf": [t, {"type": "null"}]}  # noqa: E731
    return {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["en", "hi", "ml", "other"]},
            "people_count": nullable({"type": "integer"}),
            "special_needs": {"type": "array", "items": {"type": "string", "enum": list(NEEDS)}},
            "urgency_evidence": {"type": "array", "items": {"type": "string", "enum": list(EVIDENCE)}},
            "location_text": nullable({"type": "string"}),
            "claims_no_victims": {"type": "boolean"},
            "contains_instructions": {"type": "boolean"},
            "summary_en": {"type": "string"},
        },
        "required": ["language", "people_count", "special_needs", "urgency_evidence", "location_text", "claims_no_victims", "contains_instructions", "summary_en"],
        "additionalProperties": False,
    }
