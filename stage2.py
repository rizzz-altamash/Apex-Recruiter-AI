# --- Real-Time Ranker --- 
# ------ stage2.py -------
import pandas as pd
import numpy as np
import faiss
import time
from sentence_transformers import SentenceTransformer

start_time = time.time()

print("Loading Production Artifacts...")
model = SentenceTransformer('all-MiniLM-L6-v2')
index = faiss.read_index("candidate_vectors.faiss")
meta_df = pd.read_pickle("candidate_metadata.pkl")

jd_text = """
Senior AI Engineer. Production deployment experience with embedding-based retrieval systems, 
vector databases, and hybrid search. Strong Python skills and hands-on experience with 
ranking evaluation frameworks like NDCG. Building RAG systems at product companies. 
Not a pure researcher. Needs to ship code quickly.
"""

print("Embedding Job Description...")
jd_vector = model.encode([jd_text], convert_to_numpy=True)
faiss.normalize_L2(jd_vector)

print("Querying FAISS Index...")
k_retrieval = min(150, len(meta_df)) 
distances, indices = index.search(jd_vector, k_retrieval)

PENALTY_TITLES = ['frontend', 'ui/ux', 'mechanical', 'civil', 'chemical', 'hardware', 'support']
BOOST_TITLES = ['ai', 'machine learning', 'ml', 'data', 'backend', 'recommendation', 'search', 'nlp']

results = []
for rank_pos, (faiss_idx, sim_score) in enumerate(zip(indices[0], distances[0])):
    if faiss_idx == -1: 
        continue
        
    candidate = meta_df.iloc[faiss_idx]
    
    if candidate['is_honeypot']:
        continue 
        
    title_lower = str(candidate['title']).lower()
    score_modifier = 1.0
    
    if any(p in title_lower for p in PENALTY_TITLES):
        score_modifier -= 0.25 
    elif any(b in title_lower for b in BOOST_TITLES):
        score_modifier += 0.15 
        
    behavioral_multiplier = 0.8 + (0.2 * candidate['response_rate'])
    final_score = float(sim_score * score_modifier * behavioral_multiplier)
    
    exp_formatted = round(candidate['exp_years'], 1)
    response_pct = int(candidate['response_rate'] * 100)
    reasoning = f"{candidate['title']} with {exp_formatted} yrs exp. Base semantic match adjusted by {response_pct}% response rate."
    
    if final_score > 0:
        results.append({
            "candidate_id": candidate['candidate_id'],
            "score": final_score,
            "reasoning": reasoning
        })

print("Formatting Output...")
results = sorted(results, key=lambda x: x['score'], reverse=True)
top_results = results[:100]

for i, res in enumerate(top_results):
    res['rank'] = i + 1

submission_df = pd.DataFrame(top_results)
submission_df = submission_df[['candidate_id', 'rank', 'score', 'reasoning']]

# Final submission file (CSV)
output_filename = "team_cannixaro.csv"
submission_df.to_csv(output_filename, index=False)

# Final submission file (XLSX)
output_filename = "team_cannixaro.xlsx"
submission_df.to_excel(output_filename, index=False)

print(f"✅ Production Pipeline Complete! Ranked {len(submission_df)} valid candidates.")
print(f"📄 Output saved to: {output_filename}")

elapsed_time = time.time() - start_time
print(f"⏱️  Total Execution Time: {round(elapsed_time, 2)} seconds")

print("\n--- Top 50 Candidates ---")
print(submission_df.head(50).to_string(index=False))
