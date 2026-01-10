ENRICHMENT TRIAGE APP – NEED-TO-KNOW README
========================================

This app runs miRNA / pathway enrichment, feeds the result into an LLM,
and produces a structured biological interpretation + a PDF report.

It is designed to run locally, in Docker, or on HPC via Singularity.


----------------------------------------
1) WHAT YOU NEED
----------------------------------------

• OpenAI API key  
• Docker OR Apptainer (Singularity)  

Set these environment variables in the env:

OPENAI_API_KEY=sk-xxxxx
VECTOR_STORE_ID=
----------------------------------------
2) RUNNING WITH DOCKER
----------------------------------------

Build:
docker build -t enrichment-triage .

Run:
docker run -p 5000:5000 \
  --env-file .env \
  enrichment-triage

Open in browser:
http://localhost:5000


----------------------------------------
3) RUNNING WITH APPTAINER (HPC)
----------------------------------------

Build:
apptainer build enrichment-triage.sif singularity.def

Run (important: bind a writable reports folder):
mkdir -p reports
apptainer run \
  --bind $(pwd)/reports:/reports \
  --env-file .env \
  enrichment-triage.sif

Open:
http://localhost:5000

PDFs will appear in ./reports/



----------------------------------------
4) LONG-RUNNING JOBS
----------------------------------------

LLM reasoning can take several minutes for large datasets.

Gunicorn timeout is set in the Dockerfile:
--timeout 400

If you get timeouts:
• Increase this value
• Or use fewer workers (-w 1)



----------------------------------------
5) RUNNING AN ANALYSIS (THE UI FLOW)
----------------------------------------

1. In the left “Inputs” panel:
   • Upload your Enrichr-style CSV
   • Enter the Phenotype (what you care about biologically)
   • Select Assay, Organism, Tissue, Cell Type, Perturbation, Timepoint

2. Click the blue **Analyze** button.

3. While running:
   • The backend performs enrichment triage
   • The LLM reasons about programs, confounders, and biology
   • This may take 30 seconds to several minutes for large datasets

4. When finished:
   • The Results panel populates
   • The **Programs**, **Top Terms**, and **Raw JSON** tabs become active
   • The status badge shows **Ready ✓**


----------------------------------------
6) RESULTS & PDF GENERATION
----------------------------------------

The right-side **Results** panel contains four tabs:

• **Programs**
  Shows clustered biological programs and their scores

• **Top Terms**
  Shows the most enriched gene sets and pathways

• **Raw JSON**
  Full machine-readable output (for pipelines, notebooks, etc.)

• **PDF Report**
  Human-readable biological summary


To generate a PDF:

1. Click the **PDF Report** tab
2. Click **Generate PDF**
3. When finished, the status shows **Ready ✓**
4. A preview appears in the embedded PDF viewer
5. Click **Download PDF** to save the report


Where the PDF comes from:

• The PDF is built from:
  – Enrichment programs
  – Triage scores
  – LLM interpretation (drivers, reactive, confounders)
  – Follow-up experiments

• In Docker:
  – PDFs are stored inside the container under /app/static/reports

• In Singularity:
  – PDFs are written to /reports
  – You must bind a writable folder:
        --bind ./reports:/reports

----------------------------------------
7) WHAT THE LLM RETURNS
----------------------------------------

The LLM produces free-text analysis including:
• Likely drivers vs reactive vs artifacts
• Confounders
• Follow-up experiments

The PDF builder extracts:
• Programs
• Confounders
• Follow-ups
using keyword grouping — no fragile JSON schemas.


----------------------------------------
8) TROUBLESHOOTING
----------------------------------------

If you get 500 errors:
• Check OPENAI_API_KEY is set
• Check you bound /reports for Singularity
• Check Gunicorn timeout

If PDFs fail:
• You are probably on a read-only filesystem
• Bind a writable folder to /reports


----------------------------------------
9) THIS IS AN HPC APP
----------------------------------------

This was designed for:
• Slurm
• Apptainer
• Large gene sets
• Long-running LLM reasoning

It is not a toy web app.
Treat it like a scientific workflow service.
