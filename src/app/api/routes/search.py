import logging
from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor
from app.api.dependencies import get_db

router = APIRouter()

@router.get("/search")
def search_metabolite_mentions(
    query: str = Query(...), 
    limit: int = 10, 
    conn = Depends(get_db)
):
    """
    Returns the top-10 papers that contain the keyword (metabolite), ignoring if it is abstract or full text.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT ON (pmid)
                pmid,
                REPLACE(title, '(Abstract)', '') AS title,
                REPLACE(source_url, '_abs', '') AS source_url,
                content,
                LEFT(content, 300) || '...' AS snippet,
                ts_rank(to_tsvector('english', title || ' ' || content), websearch_to_tsquery('english', %s)) AS score
            FROM research_papers
            WHERE to_tsvector('english', title || ' ' || content) @@ websearch_to_tsquery('english', %s)
            ORDER BY pmid, score DESC
            LIMIT %s;
        """, (query, query, limit))
        
        return {"results": cur.fetchall()}
    