import os
import re
import json
from pathlib import Path
from typing import List, Optional, Literal, Any, Dict
import logging
from anthropic import APIStatusError, AsyncAnthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="Interview Transcript Evaluator")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
SKILL_FILE = Path(os.getenv("SKILL_FILE", "SKILL.md"))

anthropic_client: Optional[AsyncAnthropic] = None


def load_skill_md() -> str:
    if not SKILL_FILE.exists():
        raise RuntimeError(f"SKILL.md not found: {SKILL_FILE.resolve()}")
    content = SKILL_FILE.read_text(encoding="utf-8").strip()
    if not content:
        raise RuntimeError("SKILL.md is empty")
    return content


def build_system_prompt(skill_md: str) -> str:
    return f"""
You are an expert software engineering interview evaluator.

Use the following evaluation rubric exactly as the source of truth:

{skill_md}

Instructions:
1. Evaluate only from transcript evidence.
2. Do not invent missing evidence.
3. Never make assumptions about the candidate's skills or experience beyond what is in the transcript.
4. Never frabricate evidence.
5. Every score must be supported by at least one evidence item.
6. If no evidence exists for a category, set score conservatively and explain why.
7. If evidence is weak or absent, explicitly say so and lower confidence.
8. Penalize contradictions, vagueness, and unsupported claims.
9. Prefer exact quotes when available.
10. Return valid JSON only.
11. Do not wrap the JSON in markdown fences.

Return this schema exactly:

{{
  "overall_recommendation": "Strong Hire | Hire | Lean Hire | Lean No Hire | No Hire",
  "confidence": "high | medium | low",
  "summary": "short summary",
  "category_scores": [
    {{
      "category": "Technical depth",
      "score": 1,
      "evidence": [
        {{
          "quote": "exact quote or short paraphrase",
          "why_it_matters": "reason"
        }}
      ],
      "rationale": "why this score"
    }}
  ],
  "risks_and_red_flags": [
    {{
      "issue": "red flag",
      "evidence": "quote or paraphrase",
      "severity": "low | medium | high"
    }}
  ],
  "follow_up_questions": [
    "question 1",
    "question 2"
  ]
}}
""".strip()


SKILL_MD = load_skill_md()
SYSTEM_PROMPT = build_system_prompt(SKILL_MD)


def get_anthropic_client() -> AsyncAnthropic:
    global anthropic_client

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    if not anthropic_client:
        anthropic_client = AsyncAnthropic(api_key=api_key)

    return anthropic_client


class EvaluationRequest(BaseModel):
    transcript: str = Field(..., min_length=20)
    candidate_name: Optional[str] = None
    role: Optional[str] = "Software Engineer"
    round_name: Optional[str] = None


class EvidenceItem(BaseModel):
    quote: str
    why_it_matters: str


class CategoryScore(BaseModel):
    category: str
    score: int
    evidence: List[EvidenceItem]
    rationale: str


class RiskItem(BaseModel):
    issue: str
    evidence: str
    severity: Literal["low", "medium", "high"]


class EvaluationResult(BaseModel):
    overall_recommendation: Literal["Strong Hire", "Hire", "Lean Hire", "Lean No Hire", "No Hire"]
    confidence: Literal["high", "medium", "low"]
    summary: str
    category_scores: List[CategoryScore]
    risks_and_red_flags: List[RiskItem]
    follow_up_questions: List[str]


def extract_text_content(content_blocks: List[Any]) -> str:
    return "\n".join(
        block.text
        for block in content_blocks
        if getattr(block, "type", None) == "text"
    ).strip()


async def call_claude(request: EvaluationRequest) -> Dict[str, Any]:
    user_prompt = f"""
Evaluate the following interview transcript.

Candidate: {request.candidate_name or "Unknown"}
Role: {request.role or "Software Engineer"}
Round: {request.round_name or "Unknown"}

Transcript:
\"\"\"
{request.transcript}
\"\"\"

Remember:
- Base every score on transcript evidence.
- Use lower confidence when evidence is missing.
- Return JSON only.
""".strip()

    try:
        response = await get_anthropic_client().messages.create(
            model=os.getenv("ANTHROPIC_MODEL", ANTHROPIC_MODEL),
            max_tokens=8000,
            temperature=0,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            timeout=90.0,
        )
    except APIStatusError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": "Claude API request failed", "response": exc.response.text},
        ) from exc

    text = extract_clean_json_string(extract_text_content(response.content))

    return json.loads(text)


def extract_clean_json_string(text: str) -> str:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1) if match else text.strip()
