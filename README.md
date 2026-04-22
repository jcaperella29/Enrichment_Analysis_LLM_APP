# 🧬 Enrichment Analysis LLM App

An AI-powered platform for interpreting enrichment results, prioritizing biological drivers vs confounders, and generating experiment-ready follow-up strategies using structured reasoning and literature-aware context.

---

## 🚀 Overview

This app takes enrichment outputs (e.g., GO, pathway analysis) and transforms them into:

- 🧠 **Structured biological interpretations**
- ⚖️ **Driver vs reactive vs artifact classification**
- 🔬 **Actionable follow-up experiments**
- 📄 **Publication-style PDF reports**

It is designed to reduce the gap between statistical enrichment outputs and real biological insight.

---

## 🧩 Key Features

### 🧠 1. Structured Biological Reasoning
- Identifies **likely drivers**, **reactive programs**, and **artifacts/confounders**
- Applies assay-aware interpretation (RNA-seq, scRNA-seq, etc.)
- Avoids overclaiming (e.g., RNA ≠ protein activity)

---

### 📚 2. Literature-Aware Interpretation
- Integrates **PubMed (NCBI) retrieval**
- Uses literature as **supporting context**, not blind authority
- Gracefully handles missing or weak evidence

---

### 📊 3. Program-Level Summarization
- Clusters enrichment terms into **biological programs**
- Reduces redundancy and annotation noise
- Highlights key genes driving enrichment

---

### 🔬 4. Follow-Up Experiment Design
- Suggests:
  - validation assays (qPCR, ELISA, Western, etc.)
  - mechanistic experiments (ATAC-seq, PRO-seq, etc.)
  - proper controls (e.g., antagonists, knockdown)
- Bridges computational results → experimental action

---

### 📄 5. Clean PDF Reports
- Structured interpretation sections:
  - Headline
  - Biological interpretation
  - Confounders
  - Evidence strength
  - Follow-up experiments
- Ready for sharing or discussion

---

## 🏗️ Architecture

Input enrichment table
↓
Triage (term-level scoring + flags)
↓
Program summarization (clustered biology)
↓
PubMed retrieval (NCBI E-utilities)
↓
LLM reasoning (playbook + evidence-weighted)
↓
Structured output + PDF report


---

## 🧠 Reasoning Philosophy

This app is designed to behave like a careful computational biologist:

- ❌ Avoids “pathway = activated” assumptions  
- ⚠️ Flags:
  - cell cycle artifacts
  - translation noise
  - single-gene enrichment inflation  
- ⚖️ Distinguishes:
  - **causal biology**
  - **reactive responses**
  - **technical/confounded signals**

---

## 📦 Inputs

- Enrichment results (CSV / table)
- Context:
  - organism
  - assay type
  - tissue / cell type
  - perturbation
  - timepoint
- Phenotype description

---

## 📤 Outputs

- Structured interpretation (JSON + UI)
- Program-level summary
- Evidence-weighted reasoning
- Follow-up experiment plan
- Downloadable PDF report

---

## 🔌 External Data Sources

- **PubMed (NCBI E-utilities)**  
  Used to provide literature-aware context for interpretation

- **Gene Ontology / pathway databases**  
  Used upstream in enrichment results

---

## ⚙️ Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt

2. Set environment variables

export OPENAI_API_KEY=your_key_here
export VECTOR_STORE_ID=your_vector_store_id   # optional (for RAG playbooks)
export NCBI_EMAIL=your_email                  # recommended
export NCBI_API_KEY=your_ncbi_key             # optional but faster
3. Run the app
python app.py

🧪 Example Use Case

Dataset:
Dexamethasone-treated airway epithelial cells (RNA-seq)

Output:

Weak chromatin/transcriptional reprogramming
Reactive ER/Golgi signatures
No strong anti-inflammatory enrichment at 24h
Follow-up experiments to validate GR activity
⚠️ Limitations
Enrichment is only as good as:
input gene list
statistical power
pathway coverage
RNA-seq cannot directly measure:
protein activity
phosphorylation
pathway flux
Literature retrieval is:
query-dependent
currently lightweight (v1)
🔮 Future Directions
Stronger PubMed grounding (citation extraction + scoring)
Integration with Reactome / MSigDB
Confidence scoring across evidence layers
UI improvements (cards, evidence badges)
Multi-dataset comparison

🧠 Why this matters

Enrichment tools produce lists.

Scientists need decisions.

This app helps bridge that gap by turning:

“statistical signal”

into:

“testable biological hypotheses”
