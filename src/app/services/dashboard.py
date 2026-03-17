from fastapi import APIRouter
import psycopg2
from pgvector.psycopg2 import register_vector
import os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

def get_conn():
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


@router.get("/api/dashboard/stats")
def get_dashboard_stats():
    conn = get_conn()
    try:
        with conn.cursor() as cur:

            # Total unique papers
            cur.execute("""
                SELECT COUNT(DISTINCT REPLACE(source_url, '_abs', ''))
                FROM research_papers
            """)
            total_papers = cur.fetchone()[0]

            # Full text vs abstract only
            cur.execute("""
                SELECT COUNT(DISTINCT source_url)
                FROM research_papers
                WHERE source_url NOT LIKE '%_abs'
            """)
            full_text_count = cur.fetchone()[0]

            abstract_only = total_papers - full_text_count

            # Total chunks
            cur.execute("SELECT COUNT(*) FROM research_papers")
            total_chunks = cur.fetchone()[0]

            # Average chunks per full-text paper
            cur.execute("""
                SELECT ROUND(AVG(chunk_count))
                FROM (
                    SELECT source_url, COUNT(*) as chunk_count
                    FROM research_papers
                    WHERE source_url NOT LIKE '%_abs'
                    GROUP BY source_url
                ) sub
            """)
            avg_chunks = cur.fetchone()[0] or 0

            # Top journals by paper count (extracted from DOI prefix)
            cur.execute("""
                SELECT
                    SPLIT_PART(
                        REPLACE(source_url, '_abs', ''),
                        '/', 1
                    ) as publisher,
                    COUNT(DISTINCT REPLACE(source_url, '_abs', '')) as count
                FROM research_papers
                GROUP BY publisher
                ORDER BY count DESC
                LIMIT 8
            """)
            publishers = [
                {"publisher": row[0], "count": row[1]}
                for row in cur.fetchall()
            ]

            # Most common terms in content (top keywords)
            cur.execute("""
                SELECT word, COUNT(*) as freq
                FROM (
                    SELECT regexp_split_to_table(
                        lower(content), '[^a-z]+'
                    ) as word
                    FROM research_papers
                    LIMIT 5000
                ) words
                WHERE length(word) > 5
                AND word NOT IN (
                    'parkinson','disease','patients','studies',
                    'results','methods','study','analysis',
                    'using','based','within','between','these',
                    'their','which','shown','found','after',
                    'clinical','however','including','associated',
                    'significant','compared','disease','research',
                    'also','other','further','brain','model',
                    'during','while','there','patient','group',
                    'control','figure','table','authors','being',
                    'through','without','showed', 'where', 'those',
                    'higher','lower','increase','decrease','levels',
                    'reduced','increased'
                )
                GROUP BY word
                ORDER BY freq DESC
                LIMIT 20
            """)
            keywords = [
                {"word": row[0], "count": row[1]}
                for row in cur.fetchall()
            ]

            # Papers per year (from metadata if available, else skip)
            # Chunk count distribution
            cur.execute("""
                SELECT
                    CASE
                        WHEN chunk_count BETWEEN 1 AND 5 THEN '1-5'
                        WHEN chunk_count BETWEEN 6 AND 20 THEN '6-20'
                        WHEN chunk_count BETWEEN 21 AND 50 THEN '21-50'
                        ELSE '50+'
                    END as range,
                    COUNT(*) as papers
                FROM (
                    SELECT source_url, COUNT(*) as chunk_count
                    FROM research_papers
                    WHERE source_url NOT LIKE '%_abs'
                    GROUP BY source_url
                ) sub
                GROUP BY range
                ORDER BY MIN(chunk_count)
            """)
            chunk_dist = [
                {"range": row[0], "papers": row[1]}
                for row in cur.fetchall()
            ]

        return {
            "total_papers": total_papers,
            "full_text_count": full_text_count,
            "abstract_only": abstract_only,
            "total_chunks": total_chunks,
            "avg_chunks_per_paper": int(avg_chunks),
            "publishers": publishers,
            "keywords": keywords,
            "chunk_distribution": chunk_dist,
        }

    finally:
        conn.close()