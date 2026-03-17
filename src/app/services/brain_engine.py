import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
import ollama

embedding_model = SentenceTransformer('pritamdeka/S-PubMedBert-MS-MARCO')

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

def perform_search(query, top_k=4):
    conn = get_db_connection()
    cur = conn.cursor()
    
    query_vector = embedding_model.encode(query).tolist()
    
    search_query = """
        SELECT title, source_url, content, 1 - (embedding <=> %s::vector) AS similarity
        FROM research_papers
        ORDER BY similarity DESC
        LIMIT %s;
    """
    
    cur.execute(search_query, (str(query_vector), top_k))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def atlas_chat(user_query):
    context_chunks = perform_search(user_query)
    
    context_text = ""
    for i, (title, url, content, score) in enumerate(context_chunks):
        context_text += f"\n--- Source {i+1} ---\nTitle: {title}\nDOI: {url}\nContent: {content}\n"

    system_prompt = f"""
    You are the 'Parkinson's Metabolic Atlas' Assistant (Atlas). You act ONLY as a research assistant for this database. If a user asks a question that cannot be answered by the provided RESEARCH EXCERPTS, you MUST refuse to answer and state: 'I am sorry, but that information is not available in the current Metabolic Atlas database.' Do not use any outside knowledge.
    
    INSTRUCTIONS:
    - Answer using ONLY the provided RESEARCH EXCERPTS.
    - You must always use full, grammatical sentences.
    - Always use complete sentences.
    - You must end all list items and paragraphs with proper periods or semicolons.
    - Do not say "source 1" or "source 2", state the title and DOI of the source instead.
    - Remember to never say "source 1" or "source 2", always refer to a source either by the paper's title or DOI.
    - If the answer is not in the context, say you don't know.
    - If the user asks about Parkinson's, focus on PD pathology. Clearly distinguish PD from MSA if MSA is mentioned.
    - CITATION FORMAT: Every time you make a factual claim, cite it using this format: Title (DOI).
    - Example: 'Alpha-synuclein accumulation is a hallmark of PD Research Paper Title (10.1000).'

    RESEARCH EXCERPTS:
    {context_text}
    """

    response = ollama.generate(
        model='llama3',
        system=system_prompt,
        prompt=user_query
    )

    return {
        "answer": response['response'],
        "sources": []
    }

# TEST !!!
if __name__ == "__main__":
    question = "What is the relationship between alpha-synuclein and parkinsons?"
    # question = "Who was the first president of the United States of America?"
    result = atlas_chat(question)
    print(f"ATLAS RESPONSE:\n{result['answer']}")