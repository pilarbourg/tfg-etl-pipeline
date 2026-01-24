# FOCUS: PARKINSON'S IN BRAIN TISSUE

import faiss
import json
import numpy as np
from sentence_transformers import SentenceTransformer

def search(query_text, top_k=3):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    index = faiss.read_index("data/processed/vector_db.index")
    
    with open('data/processed/chunks.json', 'r') as f:
        chunks = json.load(f)

    print(f"Query: {query_text}")
    query_vector = model.encode([query_text]).astype('float32')

    distances, indices = index.search(query_vector, top_k)

    print("\nTOP MATCHES:\n" + "="*30)
    for i, idx in enumerate(indices[0]):
        if idx != -1:
            result = chunks[idx]
            print(f"Match {i+1} (Score: {distances[0][i]:.4f})")
            print(f"Source: {result['title']} (PMID: {result['pmid']})")
            print(f"Text snippet: {result['content'][:200]}...")
            print("-" * 30)

if __name__ == "__main__":
    user_query = "What is the role of SIRT3 and mitochondrial dysfunction?"
    search(user_query)