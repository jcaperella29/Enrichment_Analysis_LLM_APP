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
