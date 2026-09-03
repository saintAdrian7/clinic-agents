import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.config import Config


@dataclass
class Knowledge:
    codes: dict
    guidelines: list
    added_codes: set

    @classmethod
    def load(cls, config: Config) -> "Knowledge":
        """Load the supplied catalogue and guidelines plus any curated additions."""
        paths = config.data.get("paths", {})
        catalog = _read_json(config.root / paths.get("catalog", "data/icd_catalog.json"))
        guidelines = _read_json(config.root / paths.get("guidelines", "data/guideline_snippets.json"))
        additions_path = config.root / paths.get("additions", "data_added/icd_additions.json")
        additions = _read_json(additions_path) if additions_path.exists() else []
        codes = {e["code"]: e for e in catalog}
        for entry in additions:
            codes.setdefault(entry["code"], entry)
        return cls(codes=codes, guidelines=guidelines,
                   added_codes={e["code"] for e in additions})

    @property
    def guideline_ids(self) -> set:
        """Ids of every guideline snippet."""
        return {g["id"] for g in self.guidelines}

    def catalog_block(self) -> str:
        """One compact line per catalogue entry; additions are labelled."""
        lines = []
        for code, e in self.codes.items():
            syn = "; ".join(e.get("synonyms") or [])
            tag = " [ADDED: not in supplied catalogue; see data_added/]" if code in self.added_codes else ""
            lines.append(f"{code} | {e['title']} | {e['chapter']} | {syn}{tag}")
        return "\n".join(lines)

    def guideline_block(self) -> str:
        """Every guideline snippet verbatim with its metadata."""
        return "\n\n".join(
            f"[{g['id']} | {g['title']} | source: {g['source']} | effective: {g['effective']}]\n{g['text']}"
            for g in self.guidelines)


def _read_json(path: Path):
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))
