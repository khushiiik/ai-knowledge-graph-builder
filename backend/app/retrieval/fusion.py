from typing import Dict, List


def reciprocal_rank_fusion(
    result_lists: List[List[Dict]], rank_constant: int = 60, top_n: int = 6
) -> List[Dict]:
    """
    Merges the semantic (Qdrant) and graph (Neo4j) result lists into one ranked
    list using Reciprocal Rank Fusion: each item's score is the sum of
    1 / (rank_constant + rank) across every list it appears in. Items are deduped by text.

    RRF over a hand-tuned weighted merge because it needs no score calibration
    between two very different systems (cosine similarity vs. graph traversal) --
    it only needs each list's relative ordering. See DECISIONS.md, Decision 5.
    """
    scored_items: Dict[str, Dict] = {}
    for result_list in result_lists:
        for rank, item in enumerate(result_list):
            key = item["text"]
            if key not in scored_items:
                scored_items[key] = {"item": item, "score": 0.0}
            scored_items[key]["score"] += 1.0 / (rank_constant + rank + 1)

    sorted_fused_entries = sorted(
        scored_items.values(),
        key=lambda fused_entry: fused_entry["score"],
        reverse=True,
    )
    return [fused_entry["item"] for fused_entry in sorted_fused_entries[:top_n]]
