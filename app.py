from dotenv import load_dotenv
import os

load_dotenv(override=True)

from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
import pandas as pd
from datetime import datetime

from summarizer import build_triage_pdf
from pipeline import run_enrichment_pipeline

app = Flask(__name__)  # expects templates/index.html by default

# ---- Upload limits ----
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB

REPORTS_DIR = os.environ.get("REPORTS_DIR") or os.path.join("/tmp", "reports")


def _safe_get(d: dict, *path, default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _build_ui_fields(result: dict, phenotype: str, context: dict) -> dict:
    gpt = result.get("gpt", {}) or {}
    display = gpt.get("display", {}) or {}

    programs = result.get("programs", {}) or {}
    program_list = programs.get("programs", []) or []

    top_program = ""
    if program_list and isinstance(program_list[0], dict):
        top_program = (
            program_list[0].get("label")
            or program_list[0].get("program")
            or program_list[0].get("name")
            or ""
        )

    gpt_summary = "\n\n".join(
        x for x in [
            display.get("headline", ""),
            display.get("experimental_context", ""),
            display.get("most_plausible_biology", ""),
        ] if x
    ).strip()

    ranked_programs = "\n\n".join(
        x for x in [
            display.get("most_plausible_biology", ""),
            display.get("likely_reactive_programs", ""),
            display.get("evidence_strength_rationale", ""),
        ] if x
    ).strip()

    confounders = "\n\n".join(
        x for x in [
            display.get("likely_artifacts_confounders", ""),
            display.get("main_uncertainties", ""),
        ] if x
    ).strip()

    follow_ups = display.get("follow_up_experiments", "")

    return {
        "phenotype": phenotype,
        "context": context,
        "programs_returned": len(program_list),
        "top_program": top_program,
        "gpt_summary": gpt_summary,
        "ranked_programs": ranked_programs,
        "confounders_to_watch": confounders,
        "follow_up_experiments": follow_ups,
        "headline": display.get("headline", ""),
        "experimental_context": display.get("experimental_context", ""),
        "raw_gpt_text": gpt.get("raw_text", ""),
    }


@app.get("/reports/<path:filename>")
def get_report(filename):
    return send_from_directory(REPORTS_DIR, filename)


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({
        "error": "Uploaded file is too large. Max allowed is 25MB."
    }), 413


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/analyze")
def analyze():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Missing file upload field 'file'."}), 400

        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"error": "No file selected."}), 400

        phenotype = request.form.get("phenotype", "").strip()
        if not phenotype:
            return jsonify({"error": "Missing phenotype."}), 400

        context = {
            "tissue": request.form.get("tissue", "").strip(),
            "cell_type": request.form.get("cell_type", "").strip(),
            "assay": request.form.get("assay", "").strip(),
            "perturbation": request.form.get("perturbation", "").strip(),
            "timepoint": request.form.get("timepoint", "").strip(),
            "organism": request.form.get("organism", "").strip(),
        }

        df = pd.read_csv(file)

        result = run_enrichment_pipeline(
            df,
            phenotype=phenotype,
            context=context,
        )

        # Make phenotype/context available at top level for downstream consumers
        result["phenotype"] = phenotype
        result["context"] = context

        # Add UI-friendly fields so frontend cards do not need to scrape raw markdown
        result["gpt_display"] = _build_ui_fields(result, phenotype, context)

        return jsonify(result)

    except Exception as e:
        import traceback
        app.logger.exception("Analyze failed")
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@app.post("/summarize")
def summarize():
    """
    Accepts triage JSON (from /analyze) and writes a PDF report into a writable reports dir.
    Returns a URL to open/embed in the UI.
    """
    try:
        triage_json = request.get_json(silent=True)
        if not isinstance(triage_json, dict):
            return jsonify({"error": "Expected JSON body (triage result dict)"}), 400

        os.makedirs(REPORTS_DIR, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"triage_report_{ts}.pdf"
        pdf_path = os.path.join(REPORTS_DIR, pdf_filename)

        phenotype = (
            _safe_get(triage_json, "programs", "meta", "phenotype")
            or _safe_get(triage_json, "gpt", "phenotype")
            or triage_json.get("phenotype")
            or ""
        )

        context = (
            triage_json.get("context")
            or _safe_get(triage_json, "programs", "meta", "context")
            or _safe_get(triage_json, "gpt", "experiment_context")
            or {}
        )
        if not isinstance(context, dict):
            context = {}

        triage_json.setdefault("gpt", {})

        if phenotype and not triage_json["gpt"].get("phenotype"):
            triage_json["gpt"]["phenotype"] = phenotype

        triage_json["gpt"]["experiment_context"] = {
            "organism": context.get("organism", ""),
            "assay": context.get("assay", ""),
            "tissue": context.get("tissue", ""),
            "cell_type": context.get("cell_type", ""),
            "perturbation": context.get("perturbation", ""),
            "timepoint": context.get("timepoint", ""),
        }

        assay = context.get("assay", "").strip()

        title = f"{assay} Enrichment Triage Report" if assay else "Enrichment Triage Report"

        build_triage_pdf(
         triage_json=triage_json,
         out_pdf_path=pdf_path,
         title=title,
         subtitle=f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        pdf_url = f"/reports/{pdf_filename}"
        return jsonify({"pdf_url": pdf_url})

    except Exception as e:
        import traceback
        app.logger.exception("Summarize failed")
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
