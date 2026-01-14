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


from pathlib import Path

PLAYBOOK_DIR = Path(__file__).resolve().parents[1] / "playbook"

ASSAY_TO_PLAYBOOK = {
    # normalize keys on input; see normalize() below
    "bulk_rnaseq": ["01_assay_confounders_rnaseq.md"],
    "scrnaseq": ["02_assay_confounders_scrna.md"],
    "perturbseq": ["10_assay_confounders_perturbseq.md"],
    "atacseq": ["11_assay_confounders_atacseq.md"],
    "mirnaseq": ["12_assay_confounders_mirnaseq.md"],
    "gwas": ["13_assay_confounders_gwas.md"],
    "dna_methylation": [
        "14_epigenetic_vs_transcriptional_priors.md",
        "15_assay_confounders_dna_methylation.md",  # <-- you create this
    ],
}

def _norm_assay(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("-", "").replace(" ", "").replace("_", "")
    # map common variants from your HTML values
    if s in ("bulkrnaseq",): return "bulk_rnaseq"
    if s in ("scrnaseq",): return "scrnaseq"
    if s in ("perturbseq",): return "perturbseq"
    if s in ("atacseq",): return "atacseq"
    if s in ("mirnaseq",): return "mirnaseq"
    if s in ("gwas",): return "gwas"
    if s in ("dnamethylation",): return "dna_methylation"
    return s

def _load_playbook_md(assay: str) -> str:
    key = _norm_assay(assay)
    files = ASSAY_TO_PLAYBOOK.get(key, [])
    chunks = []
    for fn in files:
        p = PLAYBOOK_DIR / fn
        if p.exists():
            chunks.append(f"# {fn}\n\n" + p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(chunks).strip()

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

    assay = (context or {}).get("assay", "")
    playbook_md = _load_playbook_md(assay)

    # ---- Build unified prompt ----
    prompt = f"""
Experiment context (echo this back in your answer):
{json.dumps(context, indent=2)}

Phenotype:
{phenotype}

ASSAY-SPECIFIC PLAYBOOK (authoritative rules; follow these):
{playbook_md if playbook_md else "(none found)"}

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

