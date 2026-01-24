import requests
from bs4 import BeautifulSoup
import time
import json
import os

def extract_ids():
  url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
  params = {
    "db" : "pubmed",
    "term" : "(Parkinson's Disease OR Parkinsons Disease OR Parkinson's OR Parkinsons) AND (brain tissue OR substantia nigra OR striatum) AND (metabolite OR metabolism OR biomarkers)",
    "retmax" : 3,
    "retmode" : "json"
  }
  res = requests.get(url, params=params)
  return res.json().get('esearchresult', {}).get('idlist', [])

def fetch_and_save_raw(pmid):
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
    res = requests.get(url)
    
    os.makedirs('data/raw_papers', exist_ok=True)
    file_path = f'data/raw_papers/{pmid}.xml'
    
    with open(file_path, 'wb') as f:
        f.write(res.content)
    
    soup = BeautifulSoup(res.content, "xml")
    title = soup.find('ArticleTitle').text if soup.find('ArticleTitle') else "Unknown Title"
    year = soup.find('Year').text if soup.find('Year') else "n/a"
    
    return {
        "pmid": pmid,
        "title": title,
        "year": year,
        "raw_file": file_path
    }

if __name__ == "__main__":
    ids = extract_ids()
    metadata_index = []
        
    for pmid in ids:
        entry = fetch_and_save_raw(pmid)
        metadata_index.append(entry)
        print(f"💾 Saved Raw XML & Indexed: {pmid}")
        time.sleep(0.5)

    with open('data/metadata_index.json', 'w', encoding='utf-8') as f:
        json.dump(metadata_index, f, indent=4)
    
    print(f"\nExtraction complete, papers stored in data/raw_papers")
