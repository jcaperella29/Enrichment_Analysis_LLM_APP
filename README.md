# 🧬 Enrichment Analysis LLM App

**AI-powered interpretation of enrichment results with built-in scientific skepticism, confounder awareness, and literature grounding.**

---

## 🚀 What this is

Most enrichment tools give you:

> a list of pathways

This app gives you:

> **a structured biological interpretation, evidence assessment, and an experiment plan — grounded in real literature**

---

## 🧠 Core Idea

This system acts like a **careful computational biologist**, not a hype machine.

It:
- distinguishes **causal vs reactive vs artifact signals**
- understands **assay limitations (e.g., RNA ≠ protein activity)**
- checks results against **biological expectations**
- pulls in **PubMed evidence**
- proposes **real follow-up experiments**

---

## 🔥 What makes this different

### ⚖️ 1. Driver vs Reactive vs Artifact reasoning

Instead of:

> “ER pathway enriched → ER is activated”

You get:

- Likely driver  
- Likely reactive  
- Likely artifact/confounded  

With **explicit rationale**

---

### 🧪 2. Built-in scientific guardrails

The system knows things like:

- RNA-seq cannot measure:
  - protein activity
  - phosphorylation
  - pathway flux
- cell cycle / ribosome signals are often confounders
- single-gene enrichments are weak evidence

👉 It actively prevents over-interpretation.

---

### 📚 3. Literature-aware interpretation (PubMed integrated)

- Automatically retrieves relevant papers
- Displays:
  - titles
  - PMIDs
  - links
- Uses literature as:
  - **context**, not blind authority

Example output:
Dexamethasone inhibits repair of human airway epithelial cells…
PMID: 23573276

---

### 📄 4. Clean, publication-style PDF reports

Each run produces:

- Structured interpretation
- Evidence strength assessment
- Confounder analysis
- Follow-up experiments
- Literature context

---

### 🔬 5. Actionable follow-up experiments

Not vague suggestions — real plans:

- qPCR targets
- ELISA readouts
- perturbation strategies
- proper controls

---

## 🏗️ Pipeline Overview

Enrichment Table
↓
Triage (flags, scoring, overlap quality)
↓
Program Clustering (biological grouping)
↓
PubMed Retrieval (NCBI API)
↓
LLM Reasoning (playbook + guardrails)
↓
Structured Output + PDF Report


---

## 📥 Inputs

- Enrichment results (GO / pathway tables)
- Context:
  - organism
  - assay (RNA-seq, scRNA-seq, etc.)
  - tissue / cell type
  - perturbation
  - timepoint
- Phenotype of interest

---

## 📤 Outputs

- Structured interpretation
- Program-level biology summary
- Evidence-weighted reasoning
- Follow-up experiment plan
- PDF report with citations

---

## 🧪 Example Use Case

**Dataset:**  
Dexamethasone-treated airway epithelial cells (RNA-seq)

**System conclusion:**
- Weak ER/Golgi + proteostasis changes
- Broad transcriptional remodeling
- **No strong anti-inflammatory signature detected**
- Likely reactive biology rather than direct drivers

**Literature context:**
- GILZ-mediated repair effects
- IL-8 suppression studies
- miR-375 / DUSP6 pathway

👉 Matches expectations but **does not overclaim**

---

## ⚙️ Setup

### Install

```bash
pip install -r requirements.txt

Environment Variables
OPENAI_API_KEY=your_key
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=your_ncbi_key   # optional but recommended
VECTOR_STORE_ID=your_vector_store_id  # optional

Run
python app.py

open it at
http://127.0.0.1:8050

🧠 Design Philosophy

This tool is built around one principle:

Do not lie about biology.

That means:

No hallucinated pathway activation
No overconfidence from weak enrichment
No ignoring confounders
No pretending RNA proves mechanism
⚠️ Limitations
Dependent on input enrichment quality
RNA-based → cannot infer:
protein activity
signaling dynamics
PubMed retrieval:
still lightweight (v1)
not a full citation-ranking system yet

🔮 Future Directions
Stronger literature scoring / ranking
Reactome / MSigDB integration
Multi-dataset comparison
Interactive UI improvements
Confidence scoring across evidence layers
🧬 Why this matters

Most tools stop at:

“Here are enriched pathways”

This tool answers:

“What is actually happening biologically, how confident are we, and what should we test next?”

👤 Author

John Caperella

💬 Final note

This is not just an LLM wrapper.

It is an attempt to build:

a reasoning layer between computational output and biological decision-making
