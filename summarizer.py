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
        or _get(triage_json, "phenotype")
        or ""
    )

    story.append(Paragraph("Study context", h2))
    if phenotype:
        story.append(Paragraph(f"<b>Phenotype:</b> {_safe(phenotype)}", body))
        story.append(Spacer(1, 0.12 * inch))

    ctx = _get(triage_json, "gpt.experiment_context", None)
    if not isinstance(ctx, dict):
        ctx = _get(triage_json, "context", None)
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

    # ---------------- Structured GPT interpretation ----------------
    gptv = _structured_gpt_view(triage_json)

    story.append(Paragraph("Structured interpretation", h2))

    structured_sections = [
        ("Headline", gptv["headline"]),
        ("Experimental Context", gptv["experimental_context"]),
        ("Most Plausible Biology", gptv["most_plausible_biology"]),
        ("Likely Reactive Programs", gptv["likely_reactive_programs"]),
        ("Likely Artifacts / Confounders", gptv["likely_artifacts_confounders"]),
        ("Evidence Strength and Rationale", gptv["evidence_strength_rationale"]),
        ("Follow-Up Experiments", gptv["follow_up_experiments"]),
        ("Main Uncertainties", gptv["main_uncertainties"]),
    ]

    any_structured = any(v.strip() for _, v in structured_sections)
    if any_structured:
        for heading, content in structured_sections:
            if not content.strip():
                continue
            story.append(Paragraph(heading, h3))
            _render_bullets_from_text(story, content, body)
            story.append(Spacer(1, 0.14 * inch))
    else:
        story.append(Paragraph("No structured GPT sections found.", body))
        story.append(Spacer(1, 0.14 * inch))

    story.append(Spacer(1, 0.20 * inch))

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

    # ---------------- Extracted interpretation (keyword-based, de-duplicated) ----------------
        # ---------------- Extracted interpretation (keyword-based fallback only) ----------------
    if not any(v.strip() for _, v in structured_sections):
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
        # fall back to the parsed display/sections text, but do NOT dump raw_text again
        fallback_fu = gptv["follow_up_experiments"]
        if fallback_fu.strip():
            _render_bullets_from_text(story, fallback_fu, body, max_items=30)
        else:
            story.append(Paragraph("No structured follow-up experiments returned.", body))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "<i>Note:</i> This PDF is a best-effort rendering of the triage JSON. "
        "Structured GPT fields are preferred when present; keyword-based extraction is used as a fallback.",
        body
    ))

    doc.build(story)
    

