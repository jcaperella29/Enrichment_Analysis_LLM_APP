import pandas as pd
from triage import triage_enrichment_table
from program_summarizer import summarize_programs

from reasoner import gpt5_reason_simple
from pubmed_client import fetch_pubmed_context


def run_enrichment_pipeline(
    df: pd.DataFrame,
    *,
    phenotype: str,
    context: dict,
):
    # 1) stats + biofit + gene overlap clustering
    tri = triage_enrichment_table(
        df,
        phenotype=phenotype,
        context=context,
    )

    # 2) collapse into biological programs
    programs = summarize_programs(
        tri["rows"],
        phenotype=phenotype,
    )

    # 3) retrieve literature context from PubMed / NCBI
    pubmed_context = fetch_pubmed_context(
        phenotype=phenotype,
        context=context,
        triage=tri,
        programs=programs,
    )

    # 4) GPT-5 + playbook + optional RAG + PubMed evidence
    gpt = gpt5_reason_simple(
        phenotype=phenotype,
        context=context,
        triage=tri,
        programs=programs,
        pubmed_context=pubmed_context,
    )

    return {
        "triage": tri,
        "programs": programs,
        "pubmed": pubmed_context,
        "gpt": gpt,
    }
