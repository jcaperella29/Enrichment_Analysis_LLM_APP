from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from openai import OpenAI
from schemas import claim_schema_for_prompt

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM = """You are a senior computational biologist.
Your job is to convert enrichment results into cautious, auditable biological interpretation claims.
Be strict about causal vs reactive vs artifact/confounders.
Propose follow-up experiments with concrete readouts and controls.
Use cautious, evidence-weighted language.
Never claim causality from enrichment alone.
When external literature evidence is provided, use it carefully:
- treat it as supporting context, not automatic proof
- note when literature aligns with the enrichment results
- note when literature and the current data do not align
- do not overclaim causality from literature alone
- when you refer to a retrieved paper, cite it inline as (PMID: XXXXXXXX)
"""

# Works when reasoner.py lives at project root; also tolerates older nested layout.
_HERE = Path(__file__).resolve().parent
PLAYBOOK_DIR = _HERE / "playbook"
if not PLAYBOOK_DIR.exists():
    PLAYBOOK_DIR = _HERE.parent / "playbook"

GLOBAL_PLAYBOOKS = [
    "16_evidence_weighting_and_translation.md",   # preferred production name
    "6_evidence_weighting_and_translation.md",    # tolerated older/uploaded name
    "03_growth_axis_and_overlap_rules.md",
    "08_tissue_celltype_prior_map.md",
    "09_followup_experiment_menu.md",
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
    "executive summary": "executive_summary",
    "experimental context": "experimental_context",
    "most plausible biology": "most_plausible_biology",
    "likely reactive programs": "likely_reactive_programs",
    "likely artifacts / confounders": "likely_artifacts_confounders",
    "likely artifacts/confounders": "likely_artifacts_confounders",
    "evidence strength and rationale": "evidence_strength_rationale",
    "follow-up experiments": "follow_up_experiments",
    "main uncertainties": "main_uncertainties",
    "literature context": "literature_context",
}


def _norm_assay(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("-", "").replace(" ", "").replace("_", "")
    if s in ("bulkrnaseq", "rnaseq"):
        return "bulk_rnaseq"
    if s in ("scrnaseq", "singlecellrnaseq"):
        return "scrnaseq"
    if s in ("perturbseq",):
        return "perturbseq"
    if s in ("atacseq",):
        return "atacseq"
    if s in ("mirnaseq",):
        return "mirnaseq"
    if s in ("gwas",):
        return "gwas"
    if s in ("dnamethylation", "methylation"):
        return "dna_methylation"
    return s


def _load_md_files(files: List[str]) -> str:
    chunks: List[str] = []
    seen_paths = set()
    for fn in files:
        p = PLAYBOOK_DIR / fn
        if p.exists() and p not in seen_paths:
            chunks.append(f"# {fn}\n\n" + p.read_text(encoding="utf-8"))
            seen_paths.add(p)
    return "\n\n---\n\n".join(chunks).strip()


def _load_playbook_md(assay: str) -> str:
    assay_key = _norm_assay(assay)
    assay_files = ASSAY_TO_PLAYBOOK.get(assay_key, [])
    all_files = GLOBAL_PLAYBOOKS + assay_files
    return _load_md_files(all_files)


def parse_gpt_markdown_sections(text: str) -> Dict[str, str]:
    if not text or not text.strip():
        return {}
    pattern = re.compile(r"(?ms)^##\s+(.+?)\s*$(.*?)(?=^##\s+.+?$|\Z)")
    sections: Dict[str, str] = {}
    for match in pattern.finditer(text):
        raw_heading = match.group(1).strip()
        body = match.group(2).strip()
        norm = raw_heading.lower()
        key = SECTION_ALIASES.get(norm, re.sub(r"[^a-z0-9]+", "_", norm).strip("_"))
        sections[key] = body
    return sections


def build_gpt_display_fields(gpt: Dict[str, Any]) -> Dict[str, str]:
    parsed = gpt.get("parsed", {}) or {}
    sections = gpt.get("sections", {}) or {}
    claims = parsed.get("claims", []) or []

    ranked = []
    confs = []
    validations = []
    for c in claims:
        ranked.append(f"{c.get('program', '')}: {c.get('role', 'Uncertain')} / {c.get('evidence_strength', 'Weak')} — {c.get('claim', '')}")
        for x in c.get("confounders", []) or []:
            if x not in confs:
                confs.append(x)
        for v in c.get("validation", []) or []:
            exp = v.get("experiment", "")
            readout = v.get("readout", "")
            control = v.get("control", "")
            if exp:
                validations.append(f"{exp}; readout: {readout}; control: {control}")

    return {
        "headline": parsed.get("headline") or sections.get("headline", ""),
        "experimental_context": sections.get("experimental_context", ""),
        "executive_summary": parsed.get("executive_summary", ""),
        "most_plausible_biology": "\n".join(ranked) or sections.get("most_plausible_biology", ""),
        "likely_reactive_programs": sections.get("likely_reactive_programs", ""),
        "likely_artifacts_confounders": "\n".join(confs) or sections.get("likely_artifacts_confounders", ""),
        "evidence_strength_rationale": sections.get("evidence_strength_rationale", ""),
        "follow_up_experiments": "\n".join(validations) or sections.get("follow_up_experiments", ""),
        "main_uncertainties": "\n".join(parsed.get("assay_limitations", []) or []) or sections.get("main_uncertainties", ""),
        "raw_text": gpt.get("raw_text", ""),
    }


def _compact_pubmed_context(pubmed_context: Optional[Dict[str, Any]], max_papers: int = 5) -> Dict[str, Any]:
    if not isinstance(pubmed_context, dict):
        return {}
    papers = pubmed_context.get("papers", []) or []
    compact_papers = []
    for p in papers[:max_papers]:
        if not isinstance(p, dict):
            continue
        compact_papers.append({
            "pmid": str(p.get("pmid", "")),
            "title": p.get("title", ""),
            "pubdate": p.get("pubdate", ""),
            "source": p.get("source", ""),
            "authors": (p.get("authors", []) or [])[:5],
            "abstract": (p.get("abstract", "") or "")[:2500],
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


def _extract_json_object(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if not m:
        raise ValueError("No JSON object found in model response.")
    return json.loads(m.group(0))


def _markdown_from_parsed(parsed: Dict[str, Any]) -> str:
    if parsed.get("markdown_report"):
        return parsed["markdown_report"]
    lines = ["## Headline", parsed.get("headline", ""), "", "## Executive Summary", parsed.get("executive_summary", "")]
    lines.append("\n## Claims")
    for c in parsed.get("claims", []) or []:
        lines.append(f"- **{c.get('program', '')}** [{c.get('role', 'Uncertain')} / {c.get('evidence_strength', 'Weak')}]: {c.get('claim', '')}")
    lines.append("\n## Main Confounders")
    for x in parsed.get("main_confounders", []) or []:
        lines.append(f"- {x}")
    lines.append("\n## Next Best Experiment")
    lines.append(parsed.get("next_best_experiment", ""))
    return "\n".join(lines).strip()


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
    schema = claim_schema_for_prompt()

    prompt = f"""
Return ONLY valid JSON matching this schema. Do not wrap it in markdown.

JSON schema:
{json.dumps(schema, indent=2)}

Experiment context:
{json.dumps(context, indent=2)}

Phenotype:
{phenotype}

PLAYBOOK RULES (authoritative; follow these):
{playbook_md if playbook_md else "(none found)"}

External biomedical literature context (PubMed / NCBI):
{json.dumps(pubmed_payload, indent=2)}

Enrichment summary:
{json.dumps(payload, indent=2)}

Required interpretation behavior:
- Create 3 to 8 InterpretationClaim-style claims.
- Tie every claim to supporting terms, row IDs, genes, and PMIDs when available.
- If PMIDs are only background, set literature_status to background or general_support, not direct_support.
- Separate likely drivers, likely reactive programs, likely artifact/confounded programs, and uncertain programs.
- Assign evidence_strength as Stronger, Moderate, or Weak.
- Every claim needs at least one validation experiment with a readout and control.
- Include assay limitations and top confounders.
- Use cautious language: consistent with, suggestive of, cannot distinguish from, requires validation.
""".strip()

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]

    tools = []
    if vs_id:
        tools = [{"type": "file_search", "vector_store_ids": [vs_id]}]

    # Prefer JSON mode when available; fall back to text for older SDK/model combinations.
    try:
        resp = client.responses.create(
            model=model,
            input=messages,
            tools=tools,
            text={"format": {"type": "json_schema", "name": "enrichment_interpretation", "schema": schema, "strict": False}},
        )
    except Exception:
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
        parsed = _extract_json_object(out)
        raw_text = _markdown_from_parsed(parsed)
        sections = parse_gpt_markdown_sections(raw_text)
        gpt_result = {
            "model": model,
            "raw_text": raw_text,
            "raw_json_text": out,
            "parsed": parsed,
            "sections": sections,
            "phenotype": phenotype,
            "experiment_context": context,
            "pubmed_context": pubmed_payload,
            "playbook_files_loaded_from": str(PLAYBOOK_DIR),
        }
    except Exception:
        sections = parse_gpt_markdown_sections(out)
        gpt_result = {
            "model": model,
            "raw_text": out,
            "sections": sections,
            "parsed": {},
            "phenotype": phenotype,
            "experiment_context": context,
            "pubmed_context": pubmed_payload,
            "playbook_files_loaded_from": str(PLAYBOOK_DIR),
        }

    gpt_result["display"] = build_gpt_display_fields(gpt_result)
    return gpt_result
