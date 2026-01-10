# summarizer.py
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

    # fallback
    try:
        s = str(node).strip()
        if s:
            out.append((path, s))
    except Exception:
        pass

    return out


def _bucket_by_keywords(triage_json: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Groups snippets into headings based on keywords anywhere in the JSON.
    This is intentionally forgiving: we want PDFs to render even when GPT output is messy.
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
        line = re.sub(r"\s+", " ", (line or "")).strip()
        if not line:
            return
        if line not in buckets[bucket]:
            buckets[bucket].append(line)

    texts = _walk_text(triage_json)

    for path, txt in texts:
        low = txt.lower()

        # follow-ups / experiments
        if any(k in low for k in ["follow up", "follow-up", "followup", "experiment", "validation", "knockdown", "ko ", "overexpress", "qPCR".lower()]):
            add_unique("Follow-up experiments", f"{txt}  (from {path})")
            continue

        # confounders
        if "confound" in low:
            add_unique("Confounders", f"{txt}  (from {path})")
            continue

        # verdict buckets
        if "reactive" in low:
            add_unique("Reactive", f"{txt}  (from {path})")
            continue
        if "artifact" in low:
            add_unique("Artifacts", f"{txt}  (from {path})")
            continue
        if "driver" in low:
            add_unique("Drivers", f"{txt}  (from {path})")
            continue

        # keep a little “other notes” mainly from gpt* paths
        if path.startswith("gpt"):
            add_unique("Other notes", f"{txt}  (from {path})")

    # trim so PDFs don’t get silly long
    for k in list(buckets.keys()):
        buckets[k] = buckets[k][:80]

    return buckets


# --------------------------
# Public API (what app.py imports)
# --------------------------
def build_triage_pdf(
    triage_json: Dict[str, Any],
    out_pdf_path: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> None:
    """
    Main entrypoint expected by app.py:
        from summarizer import build_triage_pdf
    """
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
    """
    Convenience helper:
    Writes a PDF into out_dir and returns (pdf_path, pdf_url).
    Assumes Flask serves /static/ at "static/".
    """
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

    # ---------------- Phenotype & Context ----------------
    phenotype = (
        _get(triage_json, "programs.meta.phenotype")
        or _get(triage_json, "gpt.phenotype")
        or ""
    )

    story.append(Paragraph("Study context", h2))
    if phenotype:
        story.append(Paragraph(f"<b>Phenotype:</b> {_safe(phenotype)}", body))
        story.append(Spacer(1, 0.12 * inch))

    # context can live in gpt.experiment_context OR (sometimes) programs.meta later
    ctx = _get(triage_json, "gpt.experiment_context", None)
    if not isinstance(ctx, dict):
        ctx = _get(triage_json, "programs.meta.experiment_context", {}) or {}

    if isinstance(ctx, dict) and ctx:
        rows = [["Field", "Value"]]
        for k in ["organism", "assay", "tissue", "cell_type", "perturbation", "timepoint"]:
            v = ctx.get(k)
            if v is not None and str(v).strip():
                rows.append([k, _safe(v)])

        t = Table(rows, colWidths=[1.8 * inch, 4.7 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#2a3555")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#0f1626")),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#e8eefc")),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No structured context found.", body))

    story.append(Spacer(1, 0.25 * inch))

    # ---------------- Program classification (structured if present) ----------------
    story.append(Paragraph("Program triage (structured, if present)", h2))

    pc = _get(triage_json, "gpt.program_classification", None)

    if isinstance(pc, dict) and any(isinstance(v, list) and v for v in pc.values()):
        for key, heading in [
            ("likely_driver", "Likely drivers"),
            ("likely_reactive", "Likely reactive"),
            ("likely_artifact", "Likely artifacts / confounded"),
        ]:
            items = pc.get(key, []) or []
            story.append(Paragraph(heading, h3))

            if not items:
                story.append(Paragraph("—", body))
                story.append(Spacer(1, 0.12 * inch))
                continue

            rows = [["Program", "Rationale"]]
            for it in items:
                if isinstance(it, dict):
                    rows.append([_safe(it.get("program", "")), _safe(it.get("why", ""))])
                else:
                    rows.append([_safe(it), ""])

            t = Table(rows, colWidths=[2.3 * inch, 4.2 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#2a3555")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#0f1626")),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#e8eefc")),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.18 * inch))
    else:
        story.append(Paragraph("No structured program_classification found in gpt.program_classification.", body))

    story.append(Spacer(1, 0.25 * inch))

    # ---------------- Programs table ----------------
    story.append(Paragraph("Programs (unsupervised)", h2))
    progs = _get(triage_json, "programs.programs", []) or []
    if isinstance(progs, list) and progs:
        rows = [["Program", "Score", "Members", "Top miRNAs / genes (subset)"]]
        for p in progs[:20]:
            if not isinstance(p, dict):
                continue
            rows.append([
                _safe(p.get("program", "")),
                f"{float(p.get('program_score', 0.0) or 0.0):.2f}",
                _safe(p.get("member_count", "")),
                ", ".join([_safe(x) for x in (p.get("top_genes") or [])[:12]]),
            ])

        t = Table(rows, colWidths=[2.2 * inch, 0.7 * inch, 0.8 * inch, 2.8 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#2a3555")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#0f1626")),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#e8eefc")),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No programs found in programs.programs.", body))

    story.append(PageBreak())

    # ---------------- Top Enriched Terms ----------------
    story.append(Paragraph("Top enriched terms", h2))
    triage_rows = _get(triage_json, "triage.rows", []) or []

    if isinstance(triage_rows, list) and triage_rows:
        triage_rows_sorted = sorted(
            triage_rows,
            key=lambda r: (r.get("combined_pre_gpt_score", r.get("triage_score", 0)) if isinstance(r, dict) else 0),
            reverse=True,
        )[:50]

        table = [["Term", "Score", "Flags", "Overlap"]]
        for r in triage_rows_sorted:
            if not isinstance(r, dict):
                continue
            score = r.get("combined_pre_gpt_score", r.get("triage_score", 0)) or 0
            flags = ", ".join([_safe(x) for x in (r.get("flags") or [])])
            overlap = (
                f"{r.get('overlap_k')}/{r.get('overlap_n')}"
                if r.get("overlap_n") else _safe(r.get("overlap_k"))
            )
            table.append([_safe(r.get("term", "")), f"{float(score):.2f}", flags, overlap])

        t = Table(table, colWidths=[3.2 * inch, 0.7 * inch, 1.6 * inch, 0.8 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#2a3555")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#0f1626")),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#e8eefc")),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No triage rows found in triage.rows.", body))

    story.append(Spacer(1, 0.25 * inch))

    # ---------------- Extracted interpretation (keyword-based) ----------------
    story.append(Paragraph("Extracted interpretation (keyword-based)", h2))
    buckets = _bucket_by_keywords(triage_json)

    for heading in ["Drivers", "Reactive", "Artifacts", "Confounders", "Follow-up experiments", "Other notes"]:
        story.append(Paragraph(heading, h3))
        items = buckets.get(heading, []) or []
        if not items:
            story.append(Paragraph("—", body))
            story.append(Spacer(1, 0.12 * inch))
            continue

        for it in items:
            story.append(Paragraph("• " + _safe(it), body))

        story.append(Spacer(1, 0.15 * inch))

    story.append(Spacer(1, 0.2 * inch))

    # ---------------- Structured Follow-ups (optional) ----------------
    story.append(Paragraph("Follow-up experiments (structured, if present)", h2))
    fus = _get(triage_json, "gpt.follow_up_experiments", []) or []

    if isinstance(fus, list) and fus:
        for fx in fus[:50]:
            if isinstance(fx, dict):
                story.append(Paragraph(f"<b>{_safe(fx.get('id',''))}</b>: {_safe(fx.get('hypothesis',''))}", body))
                story.append(Paragraph(f"Perturbation: {_safe(fx.get('perturbation',''))}", body))
                story.append(Paragraph(f"Readouts: {_safe(fx.get('readouts',''))}", body))
                story.append(Paragraph(f"Controls: {_safe(fx.get('controls',''))}", body))
                story.append(Paragraph(f"Expected if driver: {_safe(fx.get('expected_outcome_if_driver',''))}", body))
                story.append(Paragraph(f"Expected if reactive/artifact: {_safe(fx.get('expected_outcome_if_reactive_or_artifact',''))}", body))
            else:
                story.append(Paragraph(_safe(fx), body))
            story.append(Spacer(1, 0.15 * inch))
    else:
        story.append(Paragraph("No structured follow-up experiments returned.", body))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "<i>Note:</i> This PDF is a best-effort rendering of the triage JSON. "
        "Keyword-based extraction is included so the report remains useful even when LLM output is unstructured.",
        body
    ))

    doc.build(story)

    

