# app.py

from dotenv import load_dotenv
import os


load_dotenv(override=True)
from flask import Flask, request, jsonify, render_template
from werkzeug.exceptions import RequestEntityTooLarge
import pandas as pd

from datetime import datetime
from summarizer import build_triage_pdf

from flask import Flask, request, jsonify, send_from_directory

from pipeline import run_enrichment_pipeline

app = Flask(__name__)  # expects templates/index.html by default

# ---- Upload limits ----
# Set max upload size (bytes). Example: 25 MB
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB



REPORTS_DIR = os.environ.get("REPORTS_DIR") or os.path.join("/tmp", "reports")

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

        # Make sure reports dir exists (MUST be writable in Apptainer)
        os.makedirs(REPORTS_DIR, exist_ok=True)

        # Unique filename
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"triage_report_{ts}.pdf"
        pdf_path = os.path.join(REPORTS_DIR, pdf_filename)

        # -------------------------------
        # PATCH: normalize phenotype/context for PDF
        # -------------------------------
        phenotype = (
            triage_json.get("programs", {}).get("meta", {}).get("phenotype")
            or triage_json.get("gpt", {}).get("phenotype")
            or triage_json.get("phenotype")
            or ""
        )

        context = (
            triage_json.get("context")
            or triage_json.get("programs", {}).get("meta", {}).get("context")
            or triage_json.get("gpt", {}).get("experiment_context")
            or {}
        )
        if not isinstance(context, dict):
            context = {}

        triage_json.setdefault("gpt", {})

        # ensure phenotype available under gpt for PDF fallback
        if phenotype and not triage_json["gpt"].get("phenotype"):
            triage_json["gpt"]["phenotype"] = phenotype

        # ensure experiment_context exists in the exact spot the PDF expects
        triage_json["gpt"]["experiment_context"] = {
            "organism": context.get("organism", ""),
            "assay": context.get("assay", ""),
            "tissue": context.get("tissue", ""),
            "cell_type": context.get("cell_type", ""),
            "perturbation": context.get("perturbation", ""),
            "timepoint": context.get("timepoint", ""),
        }
        # -------------------------------
        # END PATCH
        # -------------------------------

        # Build PDF
        build_triage_pdf(
            triage_json=triage_json,
            out_pdf_path=pdf_path,
            title="miRNA Enrichment Triage",
            subtitle=f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Serve from our writable folder via Flask route
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

