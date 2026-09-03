import json

from pipeline.config import Config
from pipeline.knowledge import Knowledge


def _repo_config():
    """Build a Config pointing at the real repository root."""
    import pathlib
    return Config.load(pathlib.Path(__file__).resolve().parents[1])


def test_load_real_catalog_and_guidelines():
    knowledge = Knowledge.load(_repo_config())
    assert len(knowledge.codes) == 404
    assert len(knowledge.guideline_ids) == 45
    assert "BA41" in knowledge.codes


def test_additions_merged_and_tagged_in_catalog_block(tmp_path):
    config = _repo_config()
    additions_dir = tmp_path / "data_added"
    additions_dir.mkdir()
    additions_path = additions_dir / "icd_additions.json"
    additions_path.write_text(json.dumps([
        {"code": "ZZ99", "title": "Fake added condition", "chapter": "99 Testing",
         "synonyms": ["fake synonym"], "provenance": "unit test"}
    ]), encoding="utf-8")

    # Point a fresh config at tmp_path so additions resolve relative to it,
    # while reusing the real data files for catalog/guidelines.
    import shutil
    shutil.copy(config.root / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(config.root / "data", tmp_path / "data")
    tmp_config = Config.load(tmp_path)

    knowledge = Knowledge.load(tmp_config)
    assert "ZZ99" in knowledge.codes
    assert "ZZ99" in knowledge.added_codes
    block = knowledge.catalog_block()
    assert "ZZ99 | Fake added condition" in block
    assert "[ADDED: not in supplied catalogue; see data_added/]" in block
