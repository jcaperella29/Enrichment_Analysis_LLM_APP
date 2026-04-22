from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import requests


ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _norm_text(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _pick_top_program_terms(programs: Dict[str, Any], max_programs: int = 3) -> List[str]:
    out: List[str] = []
    prog_list = _safe_list(programs.get("programs"))

    for prog in prog_list[:max_programs]:
        if not isinstance(prog, dict):
            continue

        prog_name = _norm_text(prog.get("program"))
        if prog_name and prog_name != "OTHER":
            out.append(prog_name)

        rep_terms = _safe_list(prog.get("representative_terms"))
        for term_obj in rep_terms[:2]:
            if isinstance(term_obj, dict):
                term = _norm_text(term_obj.get("term"))
                if term:
                    out.append(term)

    seen = set()
    deduped = []
    for x in out:
        if x not in seen:
            deduped.append(x)
            seen.add(x)
    return deduped[:8]


def _pick_top_genes(programs: Dict[str, Any], max_genes: int = 8) -> List[str]:
    genes: List[str] = []
    prog_list = _safe_list(programs.get("programs"))

    for prog in prog_list[:3]:
        if not isinstance(prog, dict):
            continue
        for g in _safe_list(prog.get("top_genes"))[:5]:
            g = _norm_text(g)
            if g:
                genes.append(g)

    seen = set()
    deduped = []
    for g in genes:
        if g not in seen:
            deduped.append(g)
            seen.add(g)
    return deduped[:max_genes]


def _build_pubmed_query(
    *,
    phenotype: str,
    context: Dict[str, Any],
    programs: Dict[str, Any],
) -> str:
    assay = _norm_text(context.get("assay"))
    tissue = _norm_text(context.get("tissue"))
    cell_type = _norm_text(context.get("cell_type"))
    perturbation = _norm_text(context.get("perturbation"))
    organism = _norm_text(context.get("organism"))

    top_terms = _pick_top_program_terms(programs)
    top_genes = _pick_top_genes(programs)

    query_parts: List[str] = []

    if phenotype:
        query_parts.append(f'("{phenotype}"[Title/Abstract])')

    ctx_bits = []
    for x in [cell_type, tissue, perturbation, organism]:
        if x:
            ctx_bits.append(f'"{x}"[Title/Abstract]')
    if ctx_bits:
        query_parts.append("(" + " AND ".join(ctx_bits) + ")")

    if top_terms:
        term_clause = " OR ".join(f'"{t}"[Title/Abstract]' for t in top_terms[:3])
        query_parts.append(f"({term_clause})")

    if top_genes:
        gene_clause = " OR ".join(f"{g}[Title/Abstract]" for g in top_genes[:4])
        query_parts.append(f"({gene_clause})")

    if assay:
        query_parts.append(f'("{assay}"[Title/Abstract])')

    if not query_parts:
        return "biomedical literature"

    return " AND ".join(query_parts)


def _build_fallback_queries(
    *,
    phenotype: str,
    context: Dict[str, Any],
    programs: Dict[str, Any],
) -> List[str]:
    tissue = _norm_text(context.get("tissue"))
    cell_type = _norm_text(context.get("cell_type"))
    perturbation = _norm_text(context.get("perturbation"))
    organism = _norm_text(context.get("organism"))

    top_terms = _pick_top_program_terms(programs)
    top_genes = _pick_top_genes(programs)

    queries: List[str] = []

    queries.append(_build_pubmed_query(
        phenotype=phenotype,
        context=context,
        programs=programs,
    ))

    if phenotype and perturbation and (cell_type or tissue):
        queries.append(
            " ".join(x for x in [phenotype, perturbation, cell_type or tissue, organism] if x)
        )

    if perturbation and (cell_type or tissue):
        queries.append(
            " ".join(x for x in [perturbation, cell_type or tissue, organism] if x)
        )

    if perturbation and top_terms:
        queries.append(
            " ".join([perturbation] + top_terms[:3] + ([cell_type or tissue] if (cell_type or tissue) else []))
        )

    if perturbation and top_genes:
        queries.append(
            " ".join([perturbation] + top_genes[:4] + ([cell_type or tissue] if (cell_type or tissue) else []))
        )

    if perturbation:
        broad_ctx = cell_type or tissue or "airway epithelial"
        queries.append(f"{perturbation} {broad_ctx}")

    if perturbation:
        queries.append(f"{perturbation} glucocorticoid airway epithelial")
        queries.append(f"{perturbation} airway epithelium")
        queries.append(f"{perturbation} epithelial cells")
        queries.append(f"{perturbation}")

    seen = set()
    deduped = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            deduped.append(q)
            seen.add(q)

    return deduped


def _ncbi_params(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "tool": "enrichment_llm_app",
        "retmode": "json",
    }

    email = os.environ.get("NCBI_EMAIL")
    api_key = os.environ.get("NCBI_API_KEY")

    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key

    if extra:
        params.update(extra)

    return params


def _esearch(query: str, retmax: int = 5) -> List[str]:
    params = _ncbi_params({
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "sort": "relevance",
    })

    r = requests.get(ESEARCH_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("esearchresult", {}).get("idlist", [])


def _esummary(pmids: List[str]) -> List[Dict[str, Any]]:
    if not pmids:
        return []

    params = _ncbi_params({
        "db": "pubmed",
        "id": ",".join(pmids),
    })

    r = requests.get(ESUMMARY_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    result = data.get("result", {})
    out: List[Dict[str, Any]] = []

    for pmid in pmids:
        item = result.get(pmid, {})
        if not isinstance(item, dict):
            continue

        out.append({
            "pmid": pmid,
            "title": _norm_text(item.get("title")),
            "pubdate": _norm_text(item.get("pubdate")),
            "source": _norm_text(item.get("source")),
            "authors": [a.get("name", "") for a in item.get("authors", []) if isinstance(a, dict)],
            "doi": _norm_text(item.get("elocationid")),
        })

    return out


def _efetch_abstracts(pmids: List[str]) -> Dict[str, str]:
    if not pmids:
        return {}

    params = _ncbi_params({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    })

    r = requests.get(EFETCH_URL, params=params, timeout=25)
    r.raise_for_status()

    abstracts: Dict[str, str] = {}
    root = ET.fromstring(r.text)

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not (pmid_el.text or "").strip():
            continue

        pmid = pmid_el.text.strip()
        abstract_nodes = article.findall(".//Abstract/AbstractText")

        parts: List[str] = []
        for node in abstract_nodes:
            text = "".join(node.itertext()).strip()
            label = node.attrib.get("Label", "").strip()
            if text:
                if label:
                    parts.append(f"{label}: {text}")
                else:
                    parts.append(text)

        abstracts[pmid] = " ".join(parts).strip()

    return abstracts


def _with_retry_esummary(pmids: List[str], retries: int = 1, delay_s: float = 1.2) -> List[Dict[str, Any]]:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _esummary(pmids)
        except requests.HTTPError as e:
            last_exc = e
            if "429" in str(e) and attempt < retries:
                time.sleep(delay_s)
                continue
            raise
    if last_exc:
        raise last_exc
    return []


def _with_retry_abstracts(pmids: List[str], retries: int = 1, delay_s: float = 1.2) -> Dict[str, str]:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _efetch_abstracts(pmids)
        except requests.HTTPError as e:
            last_exc = e
            if "429" in str(e) and attempt < retries:
                time.sleep(delay_s)
                continue
            raise
    if last_exc:
        raise last_exc
    return {}


def fetch_pubmed_context(
    *,
    phenotype: str,
    context: Dict[str, Any],
    triage: Dict[str, Any],
    programs: Dict[str, Any],
    max_papers: int = 5,
) -> Dict[str, Any]:
    query_candidates = _build_fallback_queries(
        phenotype=phenotype,
        context=context,
        programs=programs,
    )

    out: Dict[str, Any] = {
        "query": query_candidates[0] if query_candidates else "",
        "query_candidates": query_candidates,
        "query_used": "",
        "query_strategy": "",
        "papers": [],
        "top_terms_used": _pick_top_program_terms(programs),
        "top_genes_used": _pick_top_genes(programs),
        "source": "PubMed via NCBI E-utilities",
        "status": "not_run",
    }

    try:
        pmids: List[str] = []
        used_query = ""
        used_strategy = ""

        for i, query in enumerate(query_candidates):
            try:
                pmids = _esearch(query, retmax=max_papers)
            except Exception as e:
                out.setdefault("search_errors", []).append({
                    "query": query,
                    "error": str(e),
                })
                pmids = []

            if pmids:
                used_query = query
                used_strategy = "strict" if i == 0 else f"fallback_{i}"
                break

        if not pmids:
            out["status"] = "no_hits"
            return out

        # brief polite pause before metadata fetch
        time.sleep(0.4)

        try:
            summaries = _with_retry_esummary(pmids, retries=1, delay_s=1.2)
        except Exception as e:
            out["status"] = "partial_error"
            out["query_used"] = used_query
            out["query_strategy"] = used_strategy
            out["error"] = f"esummary failed: {e}"

            # fallback: still expose PMIDs and PubMed URLs
            out["papers"] = [
                {
                    "pmid": pmid,
                    "title": "",
                    "pubdate": "",
                    "source": "",
                    "authors": [],
                    "doi": "",
                    "abstract": "",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
                for pmid in pmids
            ]
            return out

        time.sleep(0.4)

        try:
            abstracts = _with_retry_abstracts(pmids, retries=1, delay_s=1.2)
            abstract_status = "ok"
        except Exception as e:
            abstracts = {}
            abstract_status = "failed"
            out["abstract_error"] = str(e)

        papers: List[Dict[str, Any]] = []
        for s in summaries:
            pmid = s["pmid"]
            papers.append({
                **s,
                "abstract": abstracts.get(pmid, ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })

        out["papers"] = papers
        out["query_used"] = used_query
        out["query_strategy"] = used_strategy
        out["abstract_status"] = abstract_status
        out["status"] = "ok" if papers else "partial_error"
        return out

    except Exception as e:
        out["status"] = "error"
        out["error"] = str(e)
        return out
