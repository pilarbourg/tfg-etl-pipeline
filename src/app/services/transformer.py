import json
import os
from bs4 import BeautifulSoup

def clean_text(xml_content):
    soup = BeautifulSoup(xml_content, "xml")
    parts = soup.find_all('AbstractText')
    text = " ".join([p.text for p in parts])
    return text

def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks

def run_transform():
    with open('data/metadata_index.json', 'r') as f:
        index = json.load(f)
    
    transformed_data = []

    for entry in index:
        pmid = entry['pmid']
        file_path = entry['raw_file']
        
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_xml = f.read()
        
        full_text = clean_text(raw_xml)
        
        text_chunks = chunk_text(full_text)
        
        for i, chunk in enumerate(text_chunks):
            transformed_data.append({
                "chunk_id": f"{pmid}_{i}",
                "pmid": pmid,
                "title": entry['title'],
                "content": chunk
            })
            
    os.makedirs('data/processed', exist_ok=True)
    with open('data/processed/chunks.json', 'w') as f:
        json.dump(transformed_data, f, indent=4)
    
    print(f"Created {len(transformed_data)} chunks.")

if __name__ == "__main__":
    run_transform()