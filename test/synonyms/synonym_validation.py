import json
from app.core.rag.retrieval import keyword_search, vector_search

test_set = [
    # Caffeine (Fujimaki 2018, PMID 29298852)
    ("Caffeine", "10.1212/WNL.0000000000004888", "common"),
    ("1,3,7-trimethylpurine-2,6-dione", "10.1212/WNL.0000000000004888", "iupac"),
    ("Dexitac", "10.1212/WNL.0000000000004888", "alternative"),
    # Spermine (Saiki 2019, PMID 31155745)
    ("Spermine", "10.1002/ana.25516", "common"),
    ("N,N'-bis(3-aminopropyl)butane-1,4-diamine", "10.1002/ana.25516", "iupac"),
    ("Musculamine", "10.1002/ana.25516", "alternative"),
    # Homovanillic acid (PMID 33942926)
    ("Homovanillic acid", "10.1002/mds.28608", "common"),
    ("2-(4-hydroxy-3-methoxyphenyl)acetic acid", "10.1002/mds.28608", "iupac"),
    ("Vanilacetic acid", "10.1002/mds.28608", "alternative"),
    # Hypoxanthine (Horvath 2023, PMID 37629028)
    ("Hypoxanthine", "10.3390/ijms241612849", "common"),
    ("1,7-dihydropurin-6-one", "10.3390/ijms241612849", "iupac"),
    ("Sarcine", "10.3390/ijms241612849", "alternative"),
    # Tryptophan (PMID 41872227)
    ("Tryptophan", "10.1038/s41598-025-30521-4", "common"),
    ("(2S)-2-amino-3-(1H-indol-3-yl)propanoic acid", "10.1038/s41598-025-30521-4", "iupac"),
    ("L-tryptophan", "10.1038/s41598-025-30521-4", "alternative"),
]

TOP_K = 10

def find_rank(chunks, target_doi):
    """
    Finds the retrieval position of the target DOI within the top chunk results to verify position.
    """
    target = target_doi.replace("_abs", "").lower().strip()
    for i, chunk in enumerate(chunks[:TOP_K], start=1):
        doi = chunk["meta"].get("url", "").replace("_abs", "").lower().strip()
        if doi == target:
            return i
    return None

results = []
for metabolite, doi, naming_type in test_set:
    kw_rank = find_rank(keyword_search(metabolite), doi)
    vec_rank = find_rank(vector_search(metabolite), doi)
    results.append({
        "metabolite": metabolite,
        "naming_type": naming_type,
        "keyword_rank": kw_rank,
        "vector_rank": vec_rank,
    })

with open("synonym_validation_results.json", "w") as f:
    json.dump(results, f, indent=2)