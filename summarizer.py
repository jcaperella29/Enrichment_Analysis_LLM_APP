from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors


def _safe(x: Any) -> str:
    if x is None:
        return ""
    return escape(str(x))


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "report"


def _get(d: Dict[str, Any], path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _join(values: List[Any], limit: int = 8) -> str:
    vals = [str(v) for v in (values or []) if v]
    return ", ".join(vals[:limit])


def _para(story: List[Any], text: str, style) -> None:
    story.append(Paragraph(_safe(text) if text else "—", style))


def _bullet_list(story: List[Any], items: List[str], body, limit: int = 8) -> None:
    if not items:
        story.append(Paragraph("—", body))
        return
    for item in items[:limit]:
        story.append(Paragraph("• " + _safe(item), body))


def build_triage_pdf(triage_json: Dict[str, Any], out_pdf_path: str, title: Optional[str] = None, subtitle: Optional[str] = None) -> None:
    _build_pdf(triage_json, out_pdf_path, title or "Evidence-Aware Enrichment Interpretation", subtitle)


def generate_pdf_from_triage_json(triage_json: Dict[str, Any], out_dir: str = "static/reports", filename_prefix: str = "triage_report") -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    phenotype = _get(triage_json, "programs.meta.phenotype") or _get(triage_json, "gpt.phenotype") or "enrichment triage"
    base = f"{filename_prefix}_{stamp}_{_slugify(phenotype)[:40]}.pdf"
    pdf_path = os.path.join(out_dir, base)
    pdf_url = f"/static/reports/{base}"
    build_triage_pdf(triage_json, pdf_path)
    return pdf_path, pdf_url



def _role_priority(role: str) -> int:
    x = (role or "").lower()
    if "driver" in x:
        return 4
    if "reactive" in x:
        return 3
    if "uncertain" in x:
        return 2
    if "artifact" in x or "confounded" in x:
        return 1
    return 0


def _evidence_priority(evidence_strength: str) -> int:
    x = (evidence_strength or "").lower()
    if "strong" in x:
        return 3
    if "moderate" in x:
        return 2
    if "weak" in x:
        return 1
    return 0


def _claim_priority(c: Dict[str, Any]) -> int:
    return 10 * _role_priority(c.get("role", "")) + _evidence_priority(c.get("evidence_strength", ""))


def _program_sort_key(program: Dict[str, Any], claims: List[Dict[str, Any]]) -> Tuple[int, float]:
    claim_for_prog = next((c for c in claims if c.get("program") == program.get("program")), {})
    return (_claim_priority(claim_for_prog), float(program.get("program_score", 0.0)))


def _sorted_programs_for_report(programs: List[Dict[str, Any]], claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(programs or [], key=lambda p: _program_sort_key(p, claims), reverse=True)


def _is_synthetic_positive_control(triage_json: Dict[str, Any]) -> bool:
    rows = ((triage_json.get("triage", {}) or {}).get("rows", []) or [])
    for r in rows:
        if "synthetic positive control" in str(r.get("term", "")).lower():
            return True
    # Also inspect claim evidence terms, in case triage rows are absent from a saved result.
    for c in triage_json.get("claims", []) or []:
        ev = c.get("evidence", {}) or {}
        for term in ev.get("terms", []) or []:
            if "synthetic positive control" in str(term).lower():
                return True
    return False


def _claim_heading(c: Dict[str, Any]) -> str:
    return str(c.get("program") or "Unassigned")


def _build_pdf(triage_json: Dict[str, Any], pdf_path: str, title: str, subtitle: Optional[str] = None) -> None:
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    body = styles["BodyText"]
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=10)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=title,
    )

    story: List[Any] = []
    gpt = triage_json.get("gpt", {}) or {}
    parsed = gpt.get("parsed", {}) or {}
    display = gpt.get("display", {}) or triage_json.get("gpt_display", {}) or {}
    claims = triage_json.get("claims") or []
    programs = (triage_json.get("programs", {}) or {}).get("programs", []) or []
    pubmed = triage_json.get("pubmed", {}) or {}
    metadata = triage_json.get("metadata", {}) or {}
    context = triage_json.get("context") or gpt.get("experiment_context") or {}
    synthetic_positive_control = _is_synthetic_positive_control(triage_json)
    programs_for_report = _sorted_programs_for_report(programs, claims)

    # Page 1: executive summary
    story.append(Paragraph(_safe(title), h1))
    story.append(Paragraph(_safe(subtitle or datetime.now().strftime("%Y-%m-%d %H:%M:%S")), body))
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("Executive summary", h2))
    _para(story, parsed.get("executive_summary") or display.get("executive_summary") or display.get("gpt_summary") or display.get("headline") or gpt.get("raw_text", "")[:900], body)
    if synthetic_positive_control:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph("<b>Demo input notice:</b> This run contains terms labeled synthetic positive control. Use this report to test product behavior and presentation, not as biological evidence.", body))
    story.append(Spacer(1, 0.15 * inch))

    top_driver = next((c for c in claims if (c.get("role") or "").lower().startswith("likely driver")), claims[0] if claims else None)
    biggest_confounder = ""
    for c in claims:
        if c.get("confounders"):
            biggest_confounder = c["confounders"][0]
            break
    top_exp = parsed.get("next_best_experiment") or ""
    if not top_exp:
        for c in claims:
            vals = c.get("validation") or []
            if vals:
                v = vals[0]
                top_exp = f"{v.get('experiment', '')}; readout: {v.get('readout', '')}; control: {v.get('control', '')}"
                break

    kpi_data = [
        ["Top interpretation", top_driver.get("claim", "—") if top_driver else "—"],
        ["Top driver/program", top_driver.get("program", "—") if top_driver else "—"],
        ["Biggest confounder", biggest_confounder or "—"],
        ["Recommended next experiment", top_exp or "—"],
    ]
    t = Table([[Paragraph(_safe(a), body), Paragraph(_safe(b), body)] for a, b in kpi_data], colWidths=[1.8 * inch, 4.8 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2ff")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(t)

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Run metadata", h3))
    meta_lines = [
        f"App version: {metadata.get('app_version', '—')}",
        f"Prompt version: {metadata.get('prompt_version', '—')}",
        f"Playbook version: {metadata.get('playbook_version', '—')}",
        f"Model: {metadata.get('model_name', '—')}",
        f"Input hash: {metadata.get('input_hash', '—')}",
    ]
    _bullet_list(story, meta_lines, small, limit=10)
    story.append(PageBreak())

    # Page 2: ranked programs
    story.append(Paragraph("Ranked program table", h2))
    if programs_for_report:
        rows = [["Program", "Score", "Role", "Evidence", "Key genes", "Supporting terms"]]
        for p in programs_for_report[:10]:
            claim_for_prog = next((c for c in claims if c.get("program") == p.get("program")), {})
            terms = [x.get("term", "") for x in p.get("representative_terms", [])[:3]]
            rows.append([
                p.get("program", ""),
                f"{float(p.get('program_score', 0.0)):.1f}",
                claim_for_prog.get("role", "—"),
                claim_for_prog.get("evidence_strength", "—"),
                _join(p.get("top_genes", []), 8),
                _join(terms, 3),
            ])
        table = Table([[Paragraph(_safe(str(cell)), small if i else body) for cell in row] for i, row in enumerate(rows)], colWidths=[1.35*inch, .55*inch, 1.0*inch, .75*inch, 1.5*inch, 1.6*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No program summaries available.", body))
    story.append(PageBreak())

    # Page 3: claim-evidence matrix
    story.append(Paragraph("Claim-evidence matrix", h2))
    claims_for_report = sorted(claims, key=_claim_priority, reverse=True)
    if claims_for_report:
        for idx, c in enumerate(claims_for_report[:8], 1):
            story.append(Paragraph(f"{idx}. {_safe(_claim_heading(c))}: {_safe(c.get('role', 'Uncertain'))} / {_safe(c.get('evidence_strength', 'Weak'))}", h3))
            _para(story, c.get("claim", ""), body)
            if c.get("rationale"):
                story.append(Paragraph("<b>Rationale</b>", body))
                _para(story, c.get("rationale", ""), body)
            ev = c.get("evidence", {}) or {}
            ev_rows = [
                ["Terms", _join(ev.get("terms", []), 6)],
                ["Genes", _join(ev.get("genes", []), 10)],
                ["PMIDs", _join(ev.get("pmids", []), 6)],
                ["Literature status", ev.get("literature_status", "not_assessed")],
            ]
            ev_table = Table([[Paragraph(_safe(a), small), Paragraph(_safe(b), small)] for a, b in ev_rows], colWidths=[1.3*inch, 5.3*inch])
            ev_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(ev_table)
            story.append(Spacer(1, 0.12 * inch))
    else:
        _para(story, gpt.get("raw_text", "No structured claims available."), body)
    story.append(PageBreak())

    # Page 4: confounders and assay limits
    story.append(Paragraph("Confounders and assay limitations", h2))
    story.append(Paragraph("Assay/context", h3))
    ctx_bits = [f"{k}: {v}" for k, v in context.items() if v]
    _bullet_list(story, ctx_bits, body, limit=10)
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("Main confounders", h3))
    confounders = parsed.get("main_confounders") or []
    if not confounders:
        for c in claims:
            for x in c.get("confounders", []) or []:
                if x not in confounders:
                    confounders.append(x)
    _bullet_list(story, confounders, body, limit=12)
    story.append(Paragraph("Assay limitations", h3))
    _bullet_list(story, parsed.get("assay_limitations", []), body, limit=12)
    story.append(PageBreak())

    # Page 5: validation plan + PubMed
    story.append(Paragraph("Validation plan", h2))
    seen_validation_headings = set()
    for c in claims_for_report[:8]:
        vals = c.get("validation", []) or []
        if not vals:
            continue
        heading = _claim_heading(c)
        # Avoid duplicate validation sections when GPT repeats a program. Alternative explanations
        # keep their explicit alternative label, so they remain visible without seeming duplicated.
        if heading in seen_validation_headings:
            continue
        seen_validation_headings.add(heading)
        story.append(Paragraph(_safe(heading), h3))
        for v in vals[:3]:
            _para(story, f"Experiment: {v.get('experiment', '')}; Readout: {v.get('readout', '')}; Control: {v.get('control', '')}; Expected if causal: {v.get('expected_result_if_causal', '')}", body)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Literature context (PubMed)", h2))
    papers = pubmed.get("papers", []) or []
    if not papers:
        story.append(Paragraph("No PubMed papers available for this run.", body))
    else:
        for i, p in enumerate(papers[:5], start=1):
            pmid = p.get("pmid", "") or ""
            title_p = p.get("title", "") or "Untitled"
            source = p.get("source", "") or ""
            pubdate = p.get("pubdate", "") or ""
            story.append(Paragraph(f"<b>{i}. {_safe(title_p)}</b>", body))
            story.append(Paragraph(_safe(f"PMID: {pmid} | {source} | {pubdate}"), small))
            story.append(Spacer(1, 0.08 * inch))

    doc.build(story)
