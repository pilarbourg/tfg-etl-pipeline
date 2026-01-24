import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

def run_loader():
    with open('data/processed/chunks.json', 'r') as f:
        chunks = json.load(f)

    model = SentenceTransformer('all-MiniLM-L6-v2')
    texts = [c['content'] for c in chunks]
    vectors = model.encode(texts)
    
    dimensions = vectors.shape[1]
    index = faiss.IndexFlatL2(dimensions)
    
    index.add(vectors.astype('float32'))
    
    faiss.write_index(index, "data/processed/vector_db.index")
    print(f"FAISS index created with {index.ntotal} vectors.")

if __name__ == "__main__":
    run_loader()