import os
import re
import json
from pathlib import Path
from typing import List, Optional, Literal, Any, Dict

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Interview Transcript Evaluator")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
ANTHROPIC_API_URL = os.getenv("ANTHROPIC_API_URL")
SKILL_FILE = Path(os.getenv("SKILL_FILE", "SKILL.md"))


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


def extract_text_content(response_json: Dict[str, Any]) -> str:
    blocks = response_json.get("content", [])
    return "\n".join(
        block.get("text", "")
        for block in blocks
        if block.get("type") == "text"
    ).strip()


async def call_claude(request: EvaluationRequest) -> Dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

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

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 8000,
        "temperature": 0,
        "cache_control": { "type": "ephemeral" },
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT
            }
        ],
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)

        
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={"message": "Claude API request failed", "response": response.text}
        )

    text = extract_clean_json_string(response.json())

    return json.loads(text)


def extract_clean_json_string(text: json) -> str:
    # Used to extract everything between the ```json and ``` blocks
    content = text.get("content", [])

    if content and content[0].get("type") == "text":
        content_text = content[0].get("text")

    match = re.search(r"```json\s*(.*?)\s*```", content_text, re.DOTALL)
    return match.group(1) if match else content_text.strip()
