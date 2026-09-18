"""Literature data source.

Primary: **Europe PMC** (EBI-hosted, cloud-friendly, real REST/JSON).
Fallback: NCBI E-utilities (may be blocked from datacenter IPs).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from lxml import etree

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("discoveryx.datasources.literature")

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_QUERY = "BACE1 inhibitor blood-brain barrier"
USER_AGENT = "DiscoveryX/0.1 (research; mailto:research@example.org)"


def _record_from_europepmc(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "pmcid": item.get("pmcid") or "",
        "pmid": item.get("pmid") or "",
        "doi": item.get("doi") or "",
        "title": (item.get("title") or "").strip(),
        "abstract": (item.get("abstractText") or "").strip(),
        "journal": item.get("journalTitle") or item.get("bookOrReportDetails", {}).get("publisher", ""),
        "year": str(item.get("pubYear") or ""),
        "authors": [a.strip() for a in (item.get("authorString") or "").split(",") if a.strip()][:6],
        "source": "EuropePMC",
        "cited_by": item.get("citedByCount"),
    }


def search_europepmc(query: str, *, retmax: int = 20) -> list[dict[str, Any]]:
    """Search Europe PMC and return normalised article records (real API)."""
    params = {
        "query": query,
        "format": "json",
        "pageSize": retmax,
        "resultType": "core",
    }
    try:
        with httpx.Client(timeout=45, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            resp = client.get(EUROPEPMC, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ExternalServiceError(f"Europe PMC search failed: {exc}") from exc

    results = (data.get("resultList") or {}).get("result") or []
    records = [_record_from_europepmc(r) for r in results]
    return [r for r in records if r["title"]]


# ------------------------------------------------------------------ NCBI fallback
def _ncbi_params(extra: dict[str, Any], api_key: str | None) -> dict[str, Any]:
    p = {"db": "pmc", "retmode": "json", **extra}
    if api_key:
        p["api_key"] = api_key
    return p


def search_ncbi(query: str, *, retmax: int = 20, api_key: str | None = None) -> list[str]:
    params = _ncbi_params({"term": query, "retmax": retmax, "sort": "relevance"}, api_key)
    try:
        with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
            resp = client.get(f"{EUTILS}/esearch.fcgi", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ExternalServiceError(f"NCBI esearch failed: {exc}") from exc
    return list(data.get("esearchresult", {}).get("idlist", []))


def _text(node: etree._Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _parse_articles(xml: bytes) -> list[dict[str, Any]]:
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.fromstring(xml, parser=parser)
    articles: list[dict[str, Any]] = []
    for art in root.iter("article"):
        title = _text(art.find(".//article-title"))
        abstract = " ".join(p for p in (_text(a) for a in art.findall(".//abstract")) if p)
        if not title:
            continue
        articles.append(
            {
                "pmcid": _text(art.find(".//article-id[@pub-id-type='pmc']")),
                "pmid": _text(art.find(".//article-id[@pub-id-type='pmid']")),
                "doi": _text(art.find(".//article-id[@pub-id-type='doi']")),
                "title": title,
                "abstract": abstract,
                "journal": _text(art.find(".//journal-title")),
                "year": _text(art.find(".//pub-date/year")),
                "authors": [],
                "source": "NCBI",
            }
        )
    return articles


def fetch_ncbi(pmids: list[str], *, api_key: str | None = None, batch: int = 20) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for i in range(0, len(pmids), batch):
        params = _ncbi_params({"id": ",".join(pmids[i : i + batch]), "retmode": "xml"}, api_key)
        try:
            with httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
                resp = client.get(f"{EUTILS}/efetch.fcgi", params=params)
                resp.raise_for_status()
                articles.extend(_parse_articles(resp.content))
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError(f"NCBI efetch failed: {exc}") from exc
        time.sleep(0.4 if api_key else 1.1)
    return articles


def search_and_fetch(
    query: str = DEFAULT_QUERY, *, retmax: int = 20, api_key: str | None = None
) -> list[dict[str, Any]]:
    """Search and fetch articles. Europe PMC first, NCBI as fallback."""
    try:
        records = search_europepmc(query, retmax=retmax)
        if records:
            return records
        logger.warning("Europe PMC returned no results; trying NCBI")
    except ExternalServiceError as exc:
        logger.warning("Europe PMC failed (%s); trying NCBI", exc)

    ids = search_ncbi(query, retmax=retmax, api_key=api_key)
    return fetch_ncbi(ids, api_key=api_key) if ids else []
