# analysis/pipeline.py

import pandas as pd
from triage import triage_enrichment_table
from program_summarizer import summarize_programs

from reasoner import gpt5_reason_simple


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

    # 3) GPT-5 + RAG reasoning on top (uses VECTOR_STORE_ID from env by default)
    gpt = gpt5_reason_simple(
        phenotype=phenotype,
        context=context,
        triage=tri,
        programs=programs,
    )

    return {
        "triage": tri,
        "programs": programs,
        "gpt": gpt,
    }
