# src/llm_mapper.py
import json
import requests
from typing import Dict, Any
from config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_DEPLOYMENT
)

# API version known to support GPT‑4.1 chat completions
API_VERSION = "2024-02-15-preview"

def map_entities_with_schema(extracted_text: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calls Azure OpenAI chat completions with system+user instructions,
    expects strictly valid JSON back conforming to the given schema.
    """
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_KEY}

    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured entities from raw text based on the provided schema. "
                "Return strictly valid JSON that conforms to keys and types in the schema. "
                "If a field is not found, use null or an empty value of the appropriate type. "
                "Do not include any explanations—return only the JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "JSON Schema:\n"
                f"{json.dumps(schema, indent=2)}\n\n"
                "Extract fields from the following text and map them to the schema. "
                "Return only the JSON object, no extra commentary.\n\n"
                f"TEXT:\n{extracted_text}"
            )
        }
    ]

    payload = {"messages": messages, "temperature": 0}

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    result = resp.json()

    content = result["choices"][0]["message"]["content"]
    # Parse JSON directly; if code fences present, strip and parse again
    try:
        return json.loads(content)
    except Exception:
        cleaned = content.strip().strip("`").replace("json\n", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return {"error": "Failed to parse JSON", "raw": content}