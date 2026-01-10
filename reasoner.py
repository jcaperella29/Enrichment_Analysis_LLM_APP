# llm/reasoner.py
from __future__ import annotations

import os, json
from typing import Dict, Any, Optional

from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM = """You are a senior computational biologist.
Your job: interpret enrichment results and prioritize plausible biology for the user’s phenotype.
Be strict about causal vs reactive vs artifact/confounders.
Propose follow-up experiments with concrete readouts + controls.
Write clearly.
"""

def gpt5_reason_simple(
    *,
    phenotype: str,
    context: Dict[str, Any],
    triage: Dict[str, Any],
    programs: Dict[str, Any],
    vector_store_id: Optional[str] = None,
    model: str = "gpt-5",
) -> Dict[str, Any]:
    vs_id = vector_store_id or os.environ.get("VECTOR_STORE_ID")

    payload = {
        "phenotype": phenotype,
        "experiment_context": context,
        "top_programs": (programs.get("programs") or [])[:12],
        "top_terms": (triage.get("rows") or [])[:50],
    }

    prompt = f"""
Experiment context (echo this back in your answer):
{json.dumps(context, indent=2)}

Phenotype:
{phenotype}

Enrichment summary:
{json.dumps(payload, indent=2)}

Instructions:
- Give a concise headline.
- List likely drivers vs likely reactive vs likely artifacts/confounders.
- Give follow-up experiments (readouts + controls).
- Include a confounders section.
- You may output JSON OR cleanly formatted text. Either is fine.
""".strip()

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]

    tools = []
    if vs_id:
        tools = [{"type": "file_search", "vector_store_ids": [vs_id]}]

    resp = client.responses.create(
        model=model,
        input=messages,
        tools=tools,
        # No schema here:
        text={"format": {"type": "text"}}
    )

    out = getattr(resp, "output_text", None)
    if not out:
        raise RuntimeError(f"No output_text returned. Raw response: {resp}")

    # Try to parse JSON if it happens to be JSON; otherwise store as text
    try:
        parsed = json.loads(out)
        return {"raw_text": out, "parsed": parsed}
    except Exception:
        return {"raw_text": out}
