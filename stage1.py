# --- Build Offline Index --- 
# stage1.py 
import json
import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import time
import gc   # Garbage collector to free RAM

print("Loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize the FAISS index early
dimension = 384
index = faiss.IndexFlatIP(dimension)

TRAP_TITLES = ['marketing', 'hr', 'sales', 'accountant', 'customer support', 'graphic designer', 'content writer']

print("Reading and chunking 500MB JSONL file...")
start_time = time.time()

all_metadata = []
current_documents = []
current_metadata = []

total_processed   = 0
honeypots_skipped = 0
CHUNK_SIZE    = 10000   # Process safely in chunks of 10k 

def flush_chunk_to_faiss(docs, metas):
    print(f"\n[Memory Safe] Embedding chunk of {len(docs)} valid candidates...")
    # batch_size=32 keeps CPU memory footprint extremely low
    embeddings = model.encode(docs, batch_size=32, convert_to_numpy=True, show_progress_bar=True)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    all_metadata.extend(metas)
    
    # Force clear the RAM before the next chunk
    del embeddings
    gc.collect()

with open('data/candidates.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        cand = json.loads(line)
        total_processed += 1
        
        cid = cand['candidate_id']
        profile = cand.get('profile', {})
        title = str(profile.get('current_title', '')).lower()
        exp_years = float(profile.get('years_of_experience', 0))
        signals = cand.get('redrob_signals', {})
        response_rate = float(signals.get('recruiter_response_rate', 1.0))
        
        # 1. Early Hard Filter (Saves Memory & Compute!)
        is_title_trap = any(trap in title for trap in TRAP_TITLES)
        is_dead_profile = response_rate < 0.15
        
        if is_title_trap or is_dead_profile:
            honeypots_skipped += 1
            continue # Skip completely! Do not embed.
            
        # 2. Build Semantic Document
        headline = profile.get('headline', '')
        summary = profile.get('summary', '')
        
        career_texts = []
        for job in cand.get('career_history', []):
            career_texts.append(f"{job.get('title', '')}: {job.get('description', '')}")
        career_history_str = " | ".join(career_texts)
        
        skills = cand.get('skills', [])
        trusted_skills = [
            s['name'] for s in skills 
            if s.get('endorsements', 0) > 2 or s.get('duration_months', 0) > 12
        ]
        skills_str = ", ".join(trusted_skills)
        
        semantic_doc = f"Title: {title}. Headline: {headline}. Summary: {summary}. Experience: {exp_years} years. Career: {career_history_str}. Core Skills: {skills_str}."
        
        # 3. Store in current chunk
        current_documents.append(semantic_doc)
        current_metadata.append({
            "candidate_id": cid,
            "title": profile.get('current_title', ''),
            "exp_years": exp_years,
            "response_rate": response_rate,
            "is_honeypot": False # We filtered them all out already
        })
        
        # Once we hit 10,000 valid candidates, embed them and clear RAM
        if len(current_documents) >= CHUNK_SIZE:
            flush_chunk_to_faiss(current_documents, current_metadata)
            current_documents = []
            current_metadata = []

# Flush any remaining candidates at the end of the file
if current_documents:
    flush_chunk_to_faiss(current_documents, current_metadata)

print(f"\nFinished in {round((time.time() - start_time)/60, 2)} minutes.")
print(f"Total Profiles Evaluated: {total_processed}")
print(f"Honeypots/Traps Skipped: {honeypots_skipped}")
print(f"Total Valid Candidates Indexed: {index.ntotal}")

print("\nSaving artifacts to disk...")
faiss.write_index(index, "candidate_vectors.faiss")
pd.DataFrame(all_metadata).to_pickle("candidate_metadata.pkl")
print("📄 Saved candidate_vectors.faiss & candidate_metadata.pkl")
print("✅ SUCCESS! Full dataset safely processed and indexed.")
