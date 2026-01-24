# Parkinson's Research ETL & RAG Pipeline

ETL pipeline that pulls research papers from PubMed about Parkinson's disease in brain tissue and stores them in a vector database.

## 1. Extract

Handles data from PubMed API by searching for "Parkinson's Disease" and keywords such as "brain tissue" and "metabolomics", among other terms.

Each raw XML files in data/raw_papers/ to avoid continuous calls to the API. File metadata_index.json keeps track of titles and IDs.

## 2. Transform

Cleans data via BeautifulSoup to determine the abstract text and removes all XML tags.

Splits text into chunks (approx. 500 char) with small overlap. Found in chunks.json.

## 3. Load

HuggingFace model (all-MiniLM-L6-v2) turns text chunks into vectors which are then stored locally via FAISS.

### How to Use

Requirements (requests, beautifulsoup4, sentence-transformers, faiss-cpu).

Run Pipeline:

- Run extractor.py to download papers.

- Run transformer.py to clean and chunk the text.

- Run loader.py to create the vector database.

Query: Run main.py to ask a question and find the most relevant chunks from the research.
