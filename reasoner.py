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
When external literature evidence is provided, use it carefully:
- treat it as supporting context, not automatic proof
- note when literature aligns with the enrichment results
- note when literature and the current data do not align
- do not overclaim causality from literature alone
- when you refer to a retrieved paper, cite it inline as (PMID: XXXXXXXX)
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
        r"(?ms)^##\s+(.+?)\s*$"
        r"(.*?)"
        r"(?=^##\s+.+?$|\Z)"
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


def _compact_pubmed_context(pubmed_context: Optional[Dict[str, Any]], max_papers: int = 5) -> Dict[str, Any]:
    """
    Trim PubMed payload so the prompt stays useful and not bloated.
    """
    if not isinstance(pubmed_context, dict):
        return {}

    papers = pubmed_context.get("papers", []) or []
    compact_papers = []

    for p in papers[:max_papers]:
        if not isinstance(p, dict):
            continue
        compact_papers.append({
            "pmid": p.get("pmid", ""),
            "title": p.get("title", ""),
            "pubdate": p.get("pubdate", ""),
            "source": p.get("source", ""),
            "authors": (p.get("authors", []) or [])[:5],
            "abstract": p.get("abstract", "")[:2500],
            "url": p.get("url", ""),
        })

    return {
        "status": pubmed_context.get("status", ""),
        "source": pubmed_context.get("source", "PubMed via NCBI E-utilities"),
        "query": pubmed_context.get("query", ""),
        "top_terms_used": pubmed_context.get("top_terms_used", []),
        "top_genes_used": pubmed_context.get("top_genes_used", []),
        "papers": compact_papers,
        "error": pubmed_context.get("error", ""),
    }


def gpt5_reason_simple(
    *,
    phenotype: str,
    context: Dict[str, Any],
    triage: Dict[str, Any],
    programs: Dict[str, Any],
    pubmed_context: Optional[Dict[str, Any]] = None,
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
    pubmed_payload = _compact_pubmed_context(pubmed_context)

    prompt = f"""
Experiment context (echo this back briefly in your answer):
{json.dumps(context, indent=2)}

Phenotype:
{phenotype}

PLAYBOOK RULES (authoritative; follow these):
{playbook_md if playbook_md else "(none found)"}

External biomedical literature context (PubMed / NCBI):
{json.dumps(pubmed_payload, indent=2)}

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
- Use the PubMed literature context only as supporting evidence.
- If the literature aligns with the enrichment results, say so.
- If the literature does not align with the enrichment results, say so explicitly.
- Do not pretend the literature proves the current dataset's conclusions.
- If pubmed_context.papers contains any items:
  - You MUST include a "Literature Context" section.
  - You MUST list at least 2 retrieved papers.
  - For each paper include:
    - Title (shortened if needed)
    - PMID in the format (PMID: XXXXXXXX)
  - You MUST include these papers even if they are only general background.
  - If the papers are not directly supportive, explicitly say:
    "These papers provide general background but do not directly validate this dataset."
- ONLY say "no PubMed papers were retrieved" if pubmed_context.papers is empty.
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
            "pubmed_context": pubmed_payload,
        }
    except Exception:
        sections = parse_gpt_markdown_sections(out)
        gpt_result = {
            "raw_text": out,
            "sections": sections,
            "phenotype": phenotype,
            "experiment_context": context,
            "pubmed_context": pubmed_payload,
        }

    gpt_result["display"] = build_gpt_display_fields(gpt_result)
    return gpt_result
