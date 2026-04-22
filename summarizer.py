from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib import colors


# --------------------------
# Small helpers
# --------------------------
def render_pubmed_context(story, triage_json, h2, body, Spacer, inch, Paragraph):
    pubmed = triage_json.get("pubmed", {}) or {}
    papers = pubmed.get("papers", []) or []

    story.append(Paragraph("Literature Context (PubMed)", h2))

    if not papers:
        story.append(Paragraph("No PubMed papers available for this run.", body))
        story.append(Spacer(1, 0.2 * inch))
        return

    for i, p in enumerate(papers[:5], start=1):
        pmid = p.get("pmid", "") or ""
        title = p.get("title", "") or "Untitled"
        source = p.get("source", "") or ""
        pubdate = p.get("pubdate", "") or ""
        url = p.get("url", "") or ""

        story.append(Paragraph(f"<b>{i}. {title}</b>", body))

        meta = f"PMID: {pmid}"
        if source:
            meta += f" | {source}"
        if pubdate:
            meta += f" | {pubdate}"
        story.append(Paragraph(meta, body))

        if url:
            story.append(Paragraph(f'<font color="blue">{url}</font>', body))

        story.append(Spacer(1, 0.15 * inch))

    story.append(Spacer(1, 0.25 * inch))



def _safe(x: Any) -> str:
    if x is None:
        return ""
    try:
        return str(x)
    except Exception:
        return ""


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "report"


def _get(d: Dict[str, Any], path: str, default=None):
    """
    Tiny dotted-path getter: _get(obj, "a.b.c")
    """
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _walk_text(node: Any, path: str = "") -> List[Tuple[str, str]]:
    """
    Recursively extract all string leaves from nested dict/list structures.
    Returns [(path, text), ...]
    """
    out: List[Tuple[str, str]] = []

    if node is None:
        return out

    if isinstance(node, str):
        s = node.strip()
        if s:
            out.append((path, s))
        return out

    if isinstance(node, (int, float, bool)):
        return out

    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            out.extend(_walk_text(v, p))
        return out

    if isinstance(node, list):
        for i, v in enumerate(node):
            p = f"{path}[{i}]"
            out.extend(_walk_text(v, p))
        return out

    try:
        s = str(node).strip()
        if s:
            out.append((path, s))
    except Exception:
        pass

    return out


def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("■", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _structured_gpt_view(triage_json: Dict[str, Any]) -> Dict[str, str]:
    """
    Prefer display fields first, then sections, then a few direct gpt fallbacks.
    """
    return {
        "headline": (
            _get(triage_json, "gpt_display.headline")
            or _get(triage_json, "gpt.display.headline")
            or _get(triage_json, "gpt.sections.headline")
            or ""
        ),
        "experimental_context": (
            _get(triage_json, "gpt_display.experimental_context")
            or _get(triage_json, "gpt.display.experimental_context")
            or _get(triage_json, "gpt.sections.experimental_context")
            or ""
        ),
        "most_plausible_biology": (
            _get(triage_json, "gpt_display.ranked_programs")
            or _get(triage_json, "gpt.display.most_plausible_biology")
            or _get(triage_json, "gpt.sections.most_plausible_biology")
            or ""
        ),
        "likely_reactive_programs": (
            _get(triage_json, "gpt.display.likely_reactive_programs")
            or _get(triage_json, "gpt.sections.likely_reactive_programs")
            or ""
        ),
        "likely_artifacts_confounders": (
            _get(triage_json, "gpt_display.confounders_to_watch")
            or _get(triage_json, "gpt.display.likely_artifacts_confounders")
            or _get(triage_json, "gpt.sections.likely_artifacts_confounders")
            or ""
        ),
        "evidence_strength_rationale": (
            _get(triage_json, "gpt.display.evidence_strength_rationale")
            or _get(triage_json, "gpt.sections.evidence_strength_rationale")
            or ""
        ),
        "follow_up_experiments": (
            _get(triage_json, "gpt_display.follow_up_experiments")
            or _get(triage_json, "gpt.display.follow_up_experiments")
            or _get(triage_json, "gpt.sections.follow_up_experiments")
            or ""
        ),
        "main_uncertainties": (
            _get(triage_json, "gpt.display.main_uncertainties")
            or _get(triage_json, "gpt.sections.main_uncertainties")
            or ""
        ),
        "raw_text": (
            _get(triage_json, "gpt_display.raw_gpt_text")
            or _get(triage_json, "gpt.display.raw_text")
            or _get(triage_json, "gpt.raw_text")
            or ""
        ),
    }


def _best_effort_source_for_buckets(triage_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Restrict keyword-bucket extraction so we do NOT walk the entire JSON and duplicate
    everything from gpt.display / gpt.sections / gpt_display / raw_text.
    """
    src: Dict[str, Any] = {}

    # keep only genuinely useful, non-duplicative bits
    for key in ["phenotype", "context"]:
        if key in triage_json:
            src[key] = triage_json[key]

    if "programs" in triage_json:
        src["programs"] = triage_json["programs"]

    if "triage" in triage_json:
        src["triage"] = triage_json["triage"]

    # include structured GPT follow-ups only if present as a dedicated field
    gpt_followups = _get(triage_json, "gpt.follow_up_experiments")
    if gpt_followups:
        src["gpt"] = {"follow_up_experiments": gpt_followups}

    return src


def _bucket_by_keywords(triage_json: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Groups snippets into headings based on keywords in a RESTRICTED subset of the JSON.
    This avoids the same content being rediscovered from gpt.sections, gpt.display,
    gpt_display, and gpt.raw_text all at once.
    """
    buckets: Dict[str, List[str]] = {
        "Drivers": [],
        "Reactive": [],
        "Artifacts": [],
        "Confounders": [],
        "Follow-up experiments": [],
        "Other notes": [],
    }

    def add_unique(bucket: str, line: str) -> None:
        line = _normalize_text(line)
        if not line:
            return
        if line not in buckets[bucket]:
            buckets[bucket].append(line)

    restricted = _best_effort_source_for_buckets(triage_json)
    texts = _walk_text(restricted)

    for path, txt in texts:
        low = txt.lower()

        if any(k in low for k in ["follow up", "follow-up", "followup", "experiment", "validation", "knockdown", "ko ", "overexpress", "qpcr"]):
            add_unique("Follow-up experiments", f"{txt} (from {path})")
            continue

        if "confound" in low:
            add_unique("Confounders", f"{txt} (from {path})")
            continue

        if "reactive" in low:
            add_unique("Reactive", f"{txt} (from {path})")
            continue
        if "artifact" in low:
            add_unique("Artifacts", f"{txt} (from {path})")
            continue
        if "driver" in low:
            add_unique("Drivers", f"{txt} (from {path})")
            continue

        # keep Other notes minimal; avoid dumping gpt blobs
        if path.startswith("programs") or path.startswith("triage"):
            add_unique("Other notes", f"{txt} (from {path})")

    for k in list(buckets.keys()):
        buckets[k] = buckets[k][:40]

    return buckets


def _render_bullets_from_text(story: List[Any], text: str, body, max_items: int = 20) -> None:
    text = _normalize_text(text)
    if not text:
        story.append(Paragraph("—", body))
        return

    parts = re.split(r"\s+-\s+", text)
    parts = [_normalize_text(p) for p in parts if _normalize_text(p)]

    if len(parts) <= 1:
        story.append(Paragraph(text, body))
        return

    for p in parts[:max_items]:
        story.append(Paragraph("• " + p, body))


# --------------------------
# Public API (what app.py imports)
# --------------------------
def build_triage_pdf(
    triage_json: Dict[str, Any],
    out_pdf_path: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> None:
    _build_pdf(
        triage_json=triage_json,
        pdf_path=out_pdf_path,
        title=title or "Enrichment Triage Report",
        subtitle=subtitle,
    )


def generate_pdf_from_triage_json(
    triage_json: Dict[str, Any],
    out_dir: str = "static/reports",
    filename_prefix: str = "triage_report",
) -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    phenotype = (
        _get(triage_json, "programs.meta.phenotype")
        or _get(triage_json, "gpt.phenotype")
        or "enrichment triage"
    )

    base = f"{filename_prefix}_{stamp}_{_slugify(phenotype)[:40]}.pdf"
    pdf_path = os.path.join(out_dir, base)
    pdf_url = f"/static/reports/{base}"

    build_triage_pdf(triage_json, pdf_path)
    return pdf_path, pdf_url


# --------------------------
# PDF builder
# --------------------------
def _build_pdf(
    triage_json: Dict[str, Any],
    pdf_path: str,
    title: str,
    subtitle: Optional[str] = None,
) -> None:
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from datetime import datetime

    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    body = styles["BodyText"]

    mono = ParagraphStyle(
        "mono",
        parent=styles["BodyText"],
        fontName="Courier",
        fontSize=9,
        leading=11,
    )

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title,
    )

    story: List[Any] = []

    # ---------------- Title ----------------
    story.append(Paragraph(_safe(title), h1))

    if subtitle:
        story.append(Paragraph(_safe(subtitle), body))
    else:
        story.append(Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), body))

    story.append(Spacer(1, 0.25 * inch))

    # ---------------- PubMed Literature Context ----------------
    render_pubmed_context(
        story,
        triage_json,
        h2,
        body,
        Spacer,
        inch,
        Paragraph,
    )

    # ---------------- Structured GPT interpretation ----------------
    gptv = _structured_gpt_view(triage_json)

    story.append(Paragraph("Structured interpretation", h2))

    if gptv.get("headline"):
        story.append(Paragraph("<b>Headline</b>", h3))
        story.append(Paragraph(_safe(gptv["headline"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("experimental_context"):
        story.append(Paragraph("<b>Experimental Context</b>", h3))
        story.append(Paragraph(_safe(gptv["experimental_context"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("most_plausible_biology"):
        story.append(Paragraph("<b>Most Plausible Biology</b>", h3))
        story.append(Paragraph(_safe(gptv["most_plausible_biology"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("likely_reactive_programs"):
        story.append(Paragraph("<b>Likely Reactive Programs</b>", h3))
        story.append(Paragraph(_safe(gptv["likely_reactive_programs"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("likely_artifacts_confounded"):
        story.append(Paragraph("<b>Likely Artifacts / Confounders</b>", h3))
        story.append(Paragraph(_safe(gptv["likely_artifacts_confounded"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("evidence_strength_and_rationale"):
        story.append(Paragraph("<b>Evidence Strength and Rationale</b>", h3))
        story.append(Paragraph(_safe(gptv["evidence_strength_and_rationale"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("follow_up_experiments"):
        story.append(Paragraph("<b>Follow-Up Experiments</b>", h3))
        story.append(Paragraph(_safe(gptv["follow_up_experiments"]), body))
        story.append(Spacer(1, 0.15 * inch))

    if gptv.get("main_uncertainties"):
        story.append(Paragraph("<b>Main Uncertainties</b>", h3))
        story.append(Paragraph(_safe(gptv["main_uncertainties"]), body))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Spacer(1, 0.25 * inch))

    # ---------------- Programs summary ----------------
    programs = triage_json.get("programs", {}).get("programs", [])

    if programs:
        story.append(Paragraph("Program summary", h2))

        for prog in programs[:8]:
            name = _safe(prog.get("program", "Unnamed"))
            size = prog.get("size", "")

            story.append(Paragraph(f"<b>{name}</b> (n={size})", h3))

            rep_terms = prog.get("representative_terms", [])
            if rep_terms:
                terms_str = ", ".join(
                    _safe(t.get("term", "")) for t in rep_terms[:5]
                )
                story.append(Paragraph(f"Terms: {terms_str}", body))

            genes = prog.get("top_genes", [])
            if genes:
                gene_str = ", ".join(_safe(g) for g in genes[:10])
                story.append(Paragraph(f"Top genes: {gene_str}", body))

            story.append(Spacer(1, 0.15 * inch))

    # ---------------- Build PDF ----------------
    doc.build(story)

