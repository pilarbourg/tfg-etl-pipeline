import logging
import os
import json
from psycopg2.extensions import connection
from app.services.db.connection import get_db_connection
from app.core.etl.pipeline.extract_pdf import download_pmc_pdf
from app.core.etl.pipeline.transform_pdf import process_pdf
from app.core.etl.pipeline.load_pdf import ingest_paper
from app.core.schemas.research_paper import ResearchPaper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

def run_etl_pipeline(paper: ResearchPaper, conn: connection) -> None:
    """
    Runs complete Extract-Transform-Load pipeline for a single paper.
    """
    if os.path.exists(f"results/PMC{paper.pmcid}.md"):
      logging.info(f"PMC{paper.pmcid} already processed, skipping.")
      return

    md_path = None
    if paper.pmcid:
        if download_pmc_pdf(paper.pmcid, paper.doi):
            md_path = process_pdf(paper.pmcid)
        else:
            logging.warning(f"Download failed for PMC{paper.pmcid}, storing abstract only.")
    else:
        logging.info(f"No PMCID for {paper.pmid}, storing abstract only.")

    if not paper.abstract and md_path is None:
        logging.error(f"No content available for {paper.pmid}, skipping entirely.")
        return

    ingest_paper(
        title=paper.title,
        pmid=paper.pmid,
        pmcid=paper.pmcid,
        source_id=paper.doi or paper.pmid,
        abstract=paper.abstract,
        md_path=md_path,
        conn=conn
    )

    logging.info("Successfully ran ETL pipeline.")

def run_pipeline() -> None:
    """
    Full ETL pipeline for multiple papers, in this case for the papers found in metadata_validation.json (validation set).
    """
    conn = get_db_connection()
    try:
        with open("data/metadata_validation.json", "r") as f:
            metadata = json.load(f)

        for entry in metadata:
            pmcid = entry.get("pmcid")
            
            if pmcid and os.path.exists(f"results/PMC{pmcid}.md"):
                entry["has_full_text"] = True
            else:
                entry["has_full_text"] = False

            paper = ResearchPaper(**entry)
            run_etl_pipeline(paper, conn)
            
    finally:
        conn.close()

if __name__ == "__main__":
    run_pipeline()