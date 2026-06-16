# Interview Transcript Evaluator

## Purpose
Evaluate software engineer interview transcripts and produce a structured hiring recommendation.

## Input
A transcript of one or more interview rounds.

## Output
- Overall recommendation: Strong Hire / Hire / Lean Hire / Lean No Hire / No Hire
- Category scores: 1–5
- Evidence quotes from transcript
- Risks and red flags
- Follow-up questions

## Evaluation Criteria
1. Technical depth
2. Problem solving
3. Communication
4. Collaboration
5. Adaptability
6. Product/business judgment
7. Quality mindset
8. Seniority/ownership

## Scoring Rules
- Score each category from 1 to 5.
- Base every score on transcript evidence.
- If evidence is missing, lower confidence.
- Penalize contradictions, vagueness, and hallucinated claims.
- Prefer concrete examples over general statements.

## Decision Rules
- Strong Hire: mostly 4–5, no major red flags.
- Hire: several 4s, acceptable gaps.
- Lean Hire: mixed evidence, but promising.
- Lean No Hire: multiple weak areas.
- No Hire: major gaps in core technical or behavioral areas.

## Evidence Extraction
For each category, cite:
- exact quote or paraphrase
- why it matters
- score assigned

## Red Flags
- Inability to explain decisions
- No ownership
- Poor communication
- Weak debugging or reasoning
- No examples of teamwork or learning