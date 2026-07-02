import os
import logging
from psycopg2.extensions import connection
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler(),
    ],
)

EMBEDDING_MODEL = SentenceTransformer('pritamdeka/S-PubMedBert-MS-MARCO')
EMBEDDING_MODEL.max_seq_length = 512

TEXT_SPLITTER = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
    tokenizer=EMBEDDING_MODEL.tokenizer,
    chunk_size=336,
    chunk_overlap=112,
    separators=["\n\n", "\n", "|", "-", "_", ". ", " ", ""]
)

def _already_ingested(source_id: str, conn: connection) -> bool:
    """
    Returns True if a document has already been ingested into the database.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM limited_papers WHERE source_url = %s LIMIT 1",
            (source_id,)
        )
        
        return cur.fetchone() is not None


def _store_chunks(title: str, text: str, source_id: str, pmid: str, pmcid: str | None, conn: connection) -> None:
    """
    Splits text into chunks, generates embeddings, and stores them in pgvector.
    """
    if not text:
        return
    
    text = text.replace("\x00", "") 

    chunks = TEXT_SPLITTER.split_text(text)
    embeddings = EMBEDDING_MODEL.encode(chunks).tolist()

    data_to_insert = [
        (title, source_id, pmid, pmcid, chunks[i], embeddings[i])
        for i in range(len(chunks))
    ]

    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO limited_papers
                (title, source_url, pmid, pmcid, content, embedding)
                VALUES %s
                """,
                data_to_insert
            )
        conn.commit()

    except Exception as e:
        conn.rollback()
        logging.error(f"DB insert failed: {e}")


def ingest_paper(
    title: str,
    pmid: str,
    pmcid: str,
    source_id: str,
    abstract: str | None,
    md_path: str | None,
    conn: connection
) -> None:
    """
    Ingests a single paper's abstract and full text into the pgvector database.
    """
    abs_id = source_id + "_abs"

    if abstract and not _already_ingested(abs_id, conn):
        logging.info(f"Storing abstract for {source_id}...")
        _store_chunks(title=title + " (Abstract)", pmid=pmid, pmcid=pmcid, text=abstract, source_id=abs_id, conn=conn)
    else:
        logging.info(f"Abstract already ingested or unavailable, skipping.")

    if md_path and os.path.exists(md_path) and not _already_ingested(source_id, conn):
        logging.info(f"Storing full text from {md_path}...")
        with open(md_path, "r", encoding="utf-8") as f:
            full_text = f.read()
        _store_chunks(title=title, pmid=pmid, pmcid=pmcid, text=full_text, source_id=source_id, conn=conn)
        logging.info(f"Successfully stored {source_id}.")
    else:
        logging.info(f"Full text already ingested or unavailable, skipping.")
