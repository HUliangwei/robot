from pathlib import Path
import yaml

def load_glossary(path="docs/glossary.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
