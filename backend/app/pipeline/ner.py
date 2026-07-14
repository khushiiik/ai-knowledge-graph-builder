import json
from typing import Dict, List

from app.llm.providers.factory import get_llm_provider
from app.llm.prompts.ner_prompt import build_ner_prompt


def extract_entities_and_relations(text: str) -> Dict[str, List[Dict]]:
    """
    Uses the already-configured LLM (Ollama/Groq, via the same factory as chat)
    to pull entities and relationships out of a chunk of text -- e.g. entity
    "Infosys" --WORKS_ON--> "Solar Project Gujarat".

    Chosen over a rule-based tagger (spaCy) because it needs no extra model
    download and returns relationships directly in one pass, instead of NER +
    a separate relation-extraction step. Trade-off: slower and costs tokens per
    chunk vs. a local spaCy model. See DECISIONS.md, Decision 3.
    """
    provider = get_llm_provider()
    prompt = build_ner_prompt(text)

    try:
        response = provider.llm.invoke(prompt)
        raw = str(response.content).strip()
        # Strip markdown code fences some models wrap JSON in, despite instructions
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
    except Exception:
        # Extraction is best-effort -- a malformed LLM response shouldn't fail ingestion
        return {"entities": [], "relationships": []}

    entities = [
        {"name": e["name"].strip(), "type": e.get("type", "UNKNOWN")}
        for e in data.get("entities", [])
        if e.get("name") and e["name"].strip()
    ]
    relationships = [
        {
            "source": r["source"].strip(),
            "relation": r.get("relation", "RELATED_TO").strip() or "RELATED_TO",
            "target": r["target"].strip(),
        }
        for r in data.get("relationships", [])
        if r.get("source") and r.get("target")
    ]
    return {"entities": entities, "relationships": relationships}