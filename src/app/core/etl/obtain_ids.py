import requests
import time
import json
import os
import logging
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL")

query = "Parkinson AND (metabolite OR metabolomics)"

def validate_doi(doi: str | None) -> bool:
    return bool(doi and doi.startswith("10."))

def extract_ids_paginated(batch_size: int, offset: int) -> list[str]:
    """
    Fetches a set of PMIDs from PubMed according to the defined query.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": batch_size,
        "retstart": offset,
        "retmode": "json",
        "sort": "relevance",
    }
    try:
        res = requests.get(url, params=params, timeout=20)
        res.raise_for_status()
        return res.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logging.error(f"Error fetching batch at offset {offset}: {e}")
        return []

def fetch_paper_metadata(pmid: str) -> dict | None:
    """
    Fetches metadata (title, year, DOI, and abstract) for a given PMID.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        res = requests.get(url, params=params, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "xml")

        title = soup.find("ArticleTitle")
        title = title.text if title else "Unknown Title"

        doi_tag = soup.find("ArticleId", IdType="doi")
        doi = doi_tag.text.strip() if doi_tag else None
        if not validate_doi(doi):
            logging.warning(f"Invalid/missing DOI for pmid {pmid}: {doi}")
            doi = None

        year_tag = soup.find("PubDate")
        year = year_tag.find("Year").text if year_tag and year_tag.find("Year") else "n/a"

        abstract_tags = soup.find_all("AbstractText")
        if abstract_tags:
            abstract = " ".join(tag.get_text(separator=" ") for tag in abstract_tags).strip()
        else:
            abstract = None

        return {
            "pmid": pmid,
            "doi": doi,
            "title": title,
            "year": year,
            "abstract": abstract,
            "pmcid" : None,
            "has_full_text" : False
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching pmid {pmid}: {e}")
        return None
    
def get_pmcid_from_pmid(pmid: str) -> str | None:
    """
    Obtains PMCID from PMID using the NCBI API converter.
    """
    url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    params = {
        "ids": pmid,
        "format": "json",
        "tool": "tfg_pipeline",
        "email": UNPAYWALL_EMAIL
    }
    try:
        res = requests.get(url, params=params, timeout=20)
        res.raise_for_status()
        records = res.json().get("records", [])
        if records and "pmcid" in records[0]:
            return records[0]["pmcid"].replace("PMC", "")
        return None
    except Exception as e:
        logging.error(f"Error fetching PMCID for {pmid}: {e}")
        return None
    
def get_pmid_from_pmcid(pmcid: str) -> str | None:
    """
    Gets PMID from PMCID using the NCBI API converter.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    params = {
        "dbfrom": "pmc",
        "db": "pubmed",
        "id": pmcid,
        "retmode": "json",
        "sort": "relevance",
    }
    try:
        res = requests.get(url, params=params, timeout=20)
        res.raise_for_status()
        data = res.json()

        linksets = data.get("linksets", [])
        if not linksets:
            return None

        for linksetdb in linksets[0].get("linksetdbs", []):
            if linksetdb.get("linkname") == "pmc_pubmed":
                links = linksetdb.get("links", [])
                return links[0] if links else None

        return None

    except Exception as e:
        logging.error(f"Error fetching PMID for PMC{pmcid}: {e}")
        return None
    
def build_pmid_library(max_results: int = 200) -> None:
    """
    Builds the PMID "library" of PubMed article IDs and their corresponding metadata (seen in metadata_index.json)
    Paginates through PubMed results until max_results new papers are found.
    """
    os.makedirs("data", exist_ok=True)

    out_path = "data/metadata_index.json"
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            metadata_index = json.load(f)
        existing_pmids = {e["pmid"] for e in metadata_index}
        logging.info(f"Found {len(existing_pmids)} existing papers in index")
    else:
        metadata_index = []
        existing_pmids = set()

    logging.info("Searching PubMed...")
    new_ids = []
    offset = 0
    batch_size = 20

    while len(new_ids) < max_results:
        batch = extract_ids_paginated(batch_size, offset)
        if not batch:
            logging.info("No more results from PubMed.")
            break
        for pmid in batch:
            if pmid not in existing_pmids and pmid not in new_ids:
                new_ids.append(pmid)
                if len(new_ids) >= max_results:
                    break
        offset += batch_size

    logging.info(f"Found {len(new_ids)} new PMIDs to process")

    for i, pmid in enumerate(new_ids):
        logging.info(f"[{i+1}/{len(new_ids)}] Processing PMID {pmid}")
        entry = fetch_paper_metadata(pmid)
        if not entry:
            continue
        time.sleep(5.0)
        pmcid = get_pmcid_from_pmid(pmid)
        entry["pmcid"] = pmcid
        if pmcid:
            logging.info(f"PMC full-text available: PMC{pmcid}")
            entry["has_full_text"] = True
        elif entry["abstract"]:
            logging.info(f"Abstract only (no PMC)")
        else:
            logging.warning(f"No abstract or PMC")
        metadata_index.append(entry)
        existing_pmids.add(pmid)
        time.sleep(1.0)

    logging.info("Retrying PMCID lookup for papers without full text...")
    updated = 0
    for entry in metadata_index:
        if entry.get("pmcid") is None:
            pmcid = get_pmcid_from_pmid(entry["pmid"])
            if pmcid:
                entry["pmcid"] = pmcid
                entry["has_full_text"] = True
                logging.info(f"Found PMCID for {entry['pmid']}: PMC{pmcid}")
                updated += 1
            time.sleep(5.0)
    logging.info(f"Updated {updated} papers with newly found PMCIDs")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metadata_index, f, indent=4, ensure_ascii=False)

    logging.info(f"Done. {len(metadata_index)} total papers in index ({len(new_ids)} new)")

if __name__ == "__main__":
    build_pmid_library(max_results=20)