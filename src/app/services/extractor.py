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

def validate_doi(doi):
    return bool(doi and doi.startswith("10."))


# Searches PubMed and returns list of PMIDs
def extract_ids(max_results=10):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": (
            "(Parkinson's Disease OR Parkinsons Disease) "
            "AND (substantia nigra OR striatum OR basal ganglia) "
            "AND (metabolite OR metabolomics OR biomarker)"
        ),
        "retmax": max_results,
        "retmode": "json",
    }
    res = requests.get(url, params=params, timeout=10)
    res.raise_for_status()
    return res.json().get("esearchresult", {}).get("idlist", [])


# Gets title, year, DOI, and abstract from PubMed according to PMID
def fetch_paper_metadata(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        res = requests.get(url, params=params, timeout=10)
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
            "full_text": None,
            "full_text_source": None,
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching pmid {pmid}: {e}")
        return None


# Gets PMCID from PMID to be able to use pubmed central
def get_pmcid_from_pmid(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": pmid,
        "retmode": "json",
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()

        linksets = data.get("linksets", [])
        if not linksets:
            return None

        for linksetdb in linksets[0].get("linksetdbs", []):
            if linksetdb.get("linkname") == "pubmed_pmc":
                links = linksetdb.get("links", [])
                return links[0] if links else None

        return None

    except Exception as e:
        logging.error(f"Error fetching PMCID for {pmid}: {e}")
        return None

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # Load existing index if it exists
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
    ids = extract_ids(max_results=200)
    
    # Filter out already-processed PMIDs
    new_ids = [pmid for pmid in ids if pmid not in existing_pmids]
    logging.info(f"Found {len(ids)} PMIDs, {len(new_ids)} are new")

    for i, pmid in enumerate(new_ids):
        logging.info(f"[{i+1}/{len(new_ids)}] Processing PMID {pmid}")

        entry = fetch_paper_metadata(pmid)
        if not entry:
            continue

        pmcid = get_pmcid_from_pmid(pmid)
        entry["pmcid"] = pmcid

        if pmcid:
            logging.info(f"PMC full-text available: PMC{pmcid}")
        elif entry["abstract"]:
            logging.info(f"Abstract only (no PMC)")
        else:
            logging.warning(f"No abstract or PMC")

        metadata_index.append(entry)
        time.sleep(0.4)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metadata_index, f, indent=4, ensure_ascii=False)

    logging.info(f"Done. {len(metadata_index)} total papers in index ({len(new_ids)} new)")