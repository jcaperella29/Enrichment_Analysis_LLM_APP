from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM = """You are a senior computational biologist.
Your job: interpret enrichment results and prioritize plausible biology for the user’s phenotype.
Be strict about causal vs reactive vs artifact/confounders.
Propose follow-up experiments with concrete readouts + controls.
Use cautious, evidence-weighted language.
Write clearly and in a structured way.
"""

PLAYBOOK_DIR = Path(__file__).resolve().parents[1] / "playbook"

GLOBAL_PLAYBOOKS = [
    "16_evidence_weighting_and_translation.md",
]

ASSAY_TO_PLAYBOOK = {
    "bulk_rnaseq": ["01_assay_confounders_rnaseq.md"],
    "scrnaseq": ["02_assay_confounders_scrna.md"],
    "perturbseq": ["10_assay_confounders_perturbseq.md"],
    "atacseq": ["11_assay_confounders_atacseq.md"],
    "mirnaseq": ["12_assay_confounders_mirnaseq.md"],
    "gwas": ["13_assay_confounders_gwas.md"],
    "dna_methylation": [
        "14_epigenetic_vs_transcriptional_priors.md",
        "15_assay_confounders_dna_methylation.md",
    ],
}

SECTION_ALIASES = {
    "headline": "headline",
    "experimental context": "experimental_context",
    "most plausible biology": "most_plausible_biology",
    "likely reactive programs": "likely_reactive_programs",
    "likely artifacts / confounders": "likely_artifacts_confounders",
    "likely artifacts/confounders": "likely_artifacts_confounders",
    "evidence strength and rationale": "evidence_strength_rationale",
    "follow-up experiments": "follow_up_experiments",
    "main uncertainties": "main_uncertainties",
    "confounders and alternative explanations": "confounders_and_alternatives",
}


def _norm_assay(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("-", "").replace(" ", "").replace("_", "")
    if s in ("bulkrnaseq",):
        return "bulk_rnaseq"
    if s in ("scrnaseq",):
        return "scrnaseq"
    if s in ("perturbseq",):
        return "perturbseq"
    if s in ("atacseq",):
        return "atacseq"
    if s in ("mirnaseq",):
        return "mirnaseq"
    if s in ("gwas",):
        return "gwas"
    if s in ("dnamethylation",):
        return "dna_methylation"
    return s


def _load_md_files(files: List[str]) -> str:
    chunks: List[str] = []
    for fn in files:
        p = PLAYBOOK_DIR / fn
        if p.exists():
            chunks.append(f"# {fn}\n\n" + p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(chunks).strip()


def _load_playbook_md(assay: str) -> str:
    assay_key = _norm_assay(assay)
    assay_files = ASSAY_TO_PLAYBOOK.get(assay_key, [])
    all_files = GLOBAL_PLAYBOOKS + assay_files
    return _load_md_files(all_files)


def parse_gpt_markdown_sections(text: str) -> Dict[str, str]:
    if not text or not text.strip():
        return {}

    pattern = re.compile(
        r"(?ms)^##\s+(.+?)\s*$"      # heading
        r"(.*?)"                     # body
        r"(?=^##\s+.+?$|\Z)"         # next heading or end
    )

    sections: Dict[str, str] = {}
    for match in pattern.finditer(text):
        raw_heading = match.group(1).strip()
        body = match.group(2).strip()

        norm = raw_heading.lower()
        key = SECTION_ALIASES.get(norm, re.sub(r"[^a-z0-9]+", "_", norm).strip("_"))

        sections[key] = body

    return sections


def build_gpt_display_fields(gpt: Dict[str, Any]) -> Dict[str, str]:
    sections = gpt.get("sections", {}) or {}
    parsed = gpt.get("parsed", {}) or {}

    return {
        "headline": sections.get("headline") or parsed.get("headline", ""),
        "experimental_context": sections.get("experimental_context") or parsed.get("experimental_context", ""),
        "most_plausible_biology": sections.get("most_plausible_biology") or parsed.get("most_plausible_biology", ""),
        "likely_reactive_programs": sections.get("likely_reactive_programs") or parsed.get("likely_reactive_programs", ""),
        "likely_artifacts_confounders": sections.get("likely_artifacts_confounders") or parsed.get("likely_artifacts_confounders", ""),
        "evidence_strength_rationale": sections.get("evidence_strength_rationale") or parsed.get("evidence_strength_rationale", ""),
        "follow_up_experiments": sections.get("follow_up_experiments") or parsed.get("follow_up_experiments", ""),
        "main_uncertainties": sections.get("main_uncertainties") or parsed.get("main_uncertainties", ""),
        "raw_text": gpt.get("raw_text", ""),
    }


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

    prompt = f"""
Experiment context (echo this back briefly in your answer):
{json.dumps(context, indent=2)}

Phenotype:
{phenotype}

PLAYBOOK RULES (authoritative; follow these):
{playbook_md if playbook_md else "(none found)"}

Enrichment summary:
{json.dumps(payload, indent=2)}

Instructions:
- Give a concise headline.
- Briefly restate the experimental context.
- For each major biological program, classify it as one of:
  - Likely driver
  - Likely reactive
  - Likely artifact/confounded
  - Uncertain
- For each major interpretation, indicate evidence strength as:
  - Stronger
  - Moderate
  - Weak
- Explicitly distinguish likely cell-intrinsic biology from composition/stress/QC explanations where relevant.
- Do not claim pathway activation from RNA alone when activity requires protein, phosphorylation, localization, or flux measurements.
- Include a section for confounders and alternative explanations.
- Give follow-up experiments with specific readouts and controls.
- Use cautious, evidence-weighted language.
- Output cleanly formatted markdown.

Preferred output structure:
## Headline
## Experimental Context
## Most Plausible Biology
## Likely Reactive Programs
## Likely Artifacts / Confounders
## Evidence Strength and Rationale
## Follow-Up Experiments
## Main Uncertainties
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
        text={"format": {"type": "text"}},
    )

    out = getattr(resp, "output_text", None)
    if not out:
        raise RuntimeError(f"No output_text returned. Raw response: {resp}")

    try:
        parsed = json.loads(out)
        gpt_result = {
            "raw_text": out,
            "parsed": parsed,
            "sections": {},
            "phenotype": phenotype,
            "experiment_context": context,
        }
    except Exception:
        sections = parse_gpt_markdown_sections(out)
        gpt_result = {
            "raw_text": out,
            "sections": sections,
            "phenotype": phenotype,
            "experiment_context": context,
        }

    gpt_result["display"] = build_gpt_display_fields(gpt_result)
    return gpt_result
