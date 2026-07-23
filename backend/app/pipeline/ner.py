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
        raw_response_content = str(response.content).strip()
        # Strip markdown code fences some models wrap JSON in, despite instructions
        raw_response_content = (
            raw_response_content.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        parsed_json_data = json.loads(raw_response_content)
    except Exception:
        # Extraction is best-effort -- a malformed LLM response shouldn't fail ingestion
        return {"entities": [], "relationships": []}

    entities = []
    for entity in parsed_json_data.get("entities", []):
        name = entity.get("name")
        if name and name.strip():
            entities.append(
                {"name": name.strip(), "type": entity.get("type", "UNKNOWN")}
            )

    relationships = []
    for relationship in parsed_json_data.get("relationships", []):
        source = relationship.get("source")
        target = relationship.get("target")
        if source and target:
            relation = relationship.get("relation", "RELATED_TO") or "RELATED_TO"
            relationships.append(
                {
                    "source": source.strip(),
                    "relation": relation.strip(),
                    "target": target.strip(),
                }
            )

    return {"entities": entities, "relationships": relationships}
