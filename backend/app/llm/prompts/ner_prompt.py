NER_PROMPT_TEMPLATE = """Extract named entities and relationships from the text below.
Entities: people, organizations, locations, dates, products, monetary amounts.
Relationships: how two entities are connected, expressed as a short UPPER_SNAKE_CASE
verb phrase (e.g. WORKS_ON, LOCATED_IN, OWNS, SIGNED).

Return ONLY valid JSON, no commentary, in exactly this shape:
{{
  "entities": [{{"name": "...", "type": "..."}}],
  "relationships": [{{"source": "...", "relation": "...", "target": "..."}}]
}}

If nothing relevant is found, return {{"entities": [], "relationships": []}}.

Text:
\"\"\"{text}\"\"\"
"""


def build_ner_prompt(text: str) -> str:
    # Truncate defensively -- chunks are ~500 tokens already, this just guards
    # against an oversized input (e.g. a query built from concatenated text).
    return NER_PROMPT_TEMPLATE.format(text=text[:3000])