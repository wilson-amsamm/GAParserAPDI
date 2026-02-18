import json
from pathlib import Path
from typing import List

from ga_reporter.models import PropertyConfig


def load_property_config(config_path: str) -> List[PropertyConfig]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    properties = raw.get("properties")
    if not isinstance(properties, list) or not properties:
        raise ValueError("Config must contain a non-empty 'properties' list.")

    result: List[PropertyConfig] = []
    for item in properties:
        site_name = str(item.get("site_name", "")).strip()
        property_id = str(item.get("property_id", "")).strip()
        if not site_name or not property_id:
            raise ValueError("Each property must include non-empty site_name and property_id.")
        result.append(PropertyConfig(site_name=site_name, property_id=property_id))
    return result
