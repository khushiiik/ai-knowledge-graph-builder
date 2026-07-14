from typing import Dict, List


def reciprocal_rank_fusion(result_lists: List[List[Dict]], k: int = 60, top_n: int = 6) -> List[Dict]:
    """
    Merges the semantic (Qdrant) and graph (Neo4j) result lists into one ranked
    list using Reciprocal Rank Fusion: each item's score is the sum of
    1 / (k + rank) across every list it appears in. Items are deduped by text.

    RRF over a hand-tuned weighted merge because it needs no score calibration
    between two very different systems (cosine similarity vs. graph traversal) --
    it only needs each list's relative ordering. See DECISIONS.md, Decision 5.
    """
    scored: Dict[str, Dict] = {}
    for result_list in result_lists:
        for rank, item in enumerate(result_list):
            key = item["text"]
            if key not in scored:
                scored[key] = {"item": item, "score": 0.0}
            scored[key]["score"] += 1.0 / (k + rank + 1)

    fused = sorted(scored.values(), key=lambda entry: entry["score"], reverse=True)
    return [entry["item"] for entry in fused[:top_n]]