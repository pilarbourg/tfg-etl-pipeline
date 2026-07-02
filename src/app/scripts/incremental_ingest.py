import logging
import os
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from app.services.db.connection import get_db_connection
from app.core.etl.pipeline.extract_pdf import download_pmc_pdf
from app.core.etl.pipeline.transform_pdf import process_pdf
from app.core.etl.pipeline.load_pdf import ingest_paper
from app.core.schemas.research_paper import ResearchPaper

from app.core.etl.obtain_ids import (
    fetch_paper_metadata,
    get_pmcid_from_pmid,
    query as PUBMED_QUERY,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

def get_last_run_date(conn) -> str:
    """
    Returns the date of last successful pipeline execution from the database.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM ingestion_state WHERE key = 'last_run_date'")
        row = cur.fetchone()
        return row[0] if row else "2024/01/01"

def update_last_run_date(conn, date_str: str) -> None:
    """
    Updates the pipeline checkpoint date in the database.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingestion_state (key, value, updated_at)
            VALUES ('last_run_date', %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
        """, (date_str,))
    conn.commit()

def fetch_new_pmids(since_date: str, until_date: str, max_papers: int = 10) -> list[str]:
    """
    Returns new PMIDs from PubMed E-utilities API within a window.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    pmids = []
    offset = 0
    batch_size = 100

    while len(pmids) < max_papers:
        params = {
            "db": "pubmed",
            "term": PUBMED_QUERY,
            "mindate": since_date,
            "maxdate": until_date,
            "datetype": "edat",
            "retmax": batch_size,
            "retstart": offset,
            "retmode": "json",
        }
        try:
            res = requests.get(url, params=params, timeout=20)
            res.raise_for_status()
            batch = res.json().get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            logging.error(f"PubMed query failed at offset {offset}: {e}")
            break

        if not batch:
            break

        pmids.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size
        time.sleep(1.0)

    return pmids[:max_papers]


def process_paper_end_to_end(pmid: str, conn) -> None:
    """
    Gets metadata, downloads full-text if available, processes, and ingests a single paper.
    """
    entry = fetch_paper_metadata(pmid)
    if not entry:
        return

    time.sleep(1.0)
    pmcid = get_pmcid_from_pmid(pmid)
    entry["pmcid"] = pmcid
    entry["has_full_text"] = pmcid is not None

    paper = ResearchPaper(**entry)

    md_path = None
    if paper.pmcid:
        if os.path.exists(f"results/PMC{paper.pmcid}.md"):
            logging.info(f"PMC{paper.pmcid} already processed (markdown cached), using cached version.")
            md_path = f"results/PMC{paper.pmcid}.md"
        elif download_pmc_pdf(paper.pmcid, paper.doi):
            md_path = process_pdf(paper.pmcid)
        else:
            logging.warning(f"Download failed for PMC{paper.pmcid}, storing abstract only.")
    else:
        logging.info(f"No PMCID for {pmid}, storing abstract only.")

    if not paper.abstract and md_path is None:
        logging.error(f"No content available for {pmid}, skipping entirely.")
        return

    ingest_paper(
        title=paper.title,
        pmid=paper.pmid,
        pmcid=paper.pmcid,
        source_id=paper.doi or paper.pmid,
        abstract=paper.abstract,
        md_path=md_path,
        conn=conn,
    )


def main():
    conn = get_db_connection()
    try:
        since = get_last_run_date(conn)
        today = date.today().strftime("%Y/%m/%d")

        logging.info(f"Querying PubMed for papers indexed between {since} and {today}")
        pmids = fetch_new_pmids(since, today, max_papers=10)
        logging.info(f"Found {len(pmids)} candidate PMIDs (capped at 10)")

        for i, pmid in enumerate(pmids):
            logging.info(f"[{i+1}/{len(pmids)}] Processing PMID {pmid}")
            try:
                process_paper_end_to_end(pmid, conn)
            except Exception as e:
                logging.error(f"Unhandled error processing {pmid}: {e}")
                continue
            time.sleep(1.0)

        if len(pmids) < 10:
            update_last_run_date(conn, today)
            logging.info(f"Run complete. Updated last_run_date to {today}")
        else:
            logging.info(
                f"Run complete. Cap of 10 reached — last_run_date NOT advanced. "
                f"Remaining papers in window will be processed in next run."
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()