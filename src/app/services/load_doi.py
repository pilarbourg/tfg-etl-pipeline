import json
import logging
import os
import time
from typing import Optional
from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg2.extras import execute_values

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler(),
    ],
)

embedding_model = SentenceTransformer('pritamdeka/S-PubMedBert-MS-MARCO')

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, 
    chunk_overlap=100,
    separators=["\n\n", "\n", ".", " ", ""]
)

def fetch_fulltext_pmc(pmcid: str) -> Optional[str]:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pmc", "id": pmcid, "retmode": "xml"}
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()

        soup = BeautifulSoup(res.content, "xml")

        body = soup.find("body")
        if not body:
            return None
        
        full_text = body.get_text(separator=" ", strip=True)

        for ref in body.find_all(["ref-list", "table-wrap", "fig"]):
            ref.decompose()
            
        full_text = body.get_text(separator=" ", strip=True)
        
        return full_text if len(full_text) > 200 else None

    except Exception as e:
        logging.warning(f"PMC fetch failed for PMC{pmcid}: {e}")
        return None
    

def get_db_connection():
    conn = psycopg2.connect(
        dbname="tfg_pipeline",
        user="",
        password="",
        host="localhost"
    )

    cur = conn.cursor()
    cur.execute("SET search_path TO public, extensions;")
    cur.close()

    register_vector(conn)
    return conn

def store_in_pgvector(title, text, source_url, conn):
    if not text: return
    chunks = text_splitter.split_text(text)
    
    data_to_insert = [
        (title, source_url, chunk, embedding_model.encode(chunk).tolist())
        for chunk in chunks
    ]
    
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO research_papers (title, source_url, content, embedding)
            VALUES %s
            """,
            data_to_insert
        )
    conn.commit()

def get_project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))


def ingest_all():
    conn = get_db_connection()

    try:
        root = get_project_root()
        metadata_path = os.path.join(root, "data", "metadata_index.json")

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        updated = 0

        for i, entry in enumerate(metadata):
            pmid  = entry.get("pmid")
            doi   = entry.get("doi")
            pmcid = entry.get("pmcid")

            logging.info(f"[{i+1}/{len(metadata)}] {entry.get('title', pmid)[:60]}")

            full_text        = None
            full_text_source = None

            # Abstract
            abs_url = (entry.get("doi") or entry.get("pmcid") or "N/A") + "_abs"
            if entry.get("abstract") and not already_ingested(abs_url, conn):
                logging.info(f"Storing abstract...")
                store_in_pgvector(
                    title=entry.get("title", "Unknown Title") + " (Abstract)",
                    text=entry.get("abstract"),
                    source_url=abs_url,
                    conn=conn
                )
            else:
                logging.info(f"Abstract already in DB, skipping")

            # Full text
            ft_url = entry.get("doi") or entry.get("pmcid") or "N/A"
            if pmcid and not already_ingested(ft_url, conn):
                logging.info(f"Trying PMC (PMC{pmcid})...")
                full_text = fetch_fulltext_pmc(pmcid)
                if full_text:
                    store_in_pgvector(
                        title=entry.get("title", "Unknown Title"),
                        text=full_text,
                        source_url=ft_url,
                        conn=conn
                    )
                    entry["full_text"] = full_text
                    entry["full_text_source"] = "pmc"
                    updated += 1
                time.sleep(1.5)
            else:
                logging.info(f"Full text already in DB, skipping")

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

        full_count     = sum(1 for e in metadata if e.get("full_text"))
        abstract_count = sum(1 for e in metadata if e.get("abstract"))
        logging.info(
            f"\ncompleted. {full_count}/{len(metadata)} papers have full text, "
            f"{abstract_count} have abstracts"
        )
    except Exception as e:
        logging.error(f"Pipeline crashed: {e}")
    finally:
        conn.close()
        logging.info("Database connection closed.")

def already_ingested(source_url, conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM research_papers WHERE source_url = %s LIMIT 1",
            (source_url,)
        )
        return cur.fetchone() is not None
    
if __name__ == "__main__":
    ingest_all()