"""Load variant YAML configs for eval runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

VARIANTS_DIR = Path(__file__).resolve().parent / "variants"


@dataclass
class ClassificationVariant:
    name: str
    selection_model: str | None = None
    system_prompt: str | None = None


def _variants_dir() -> Path:
    return VARIANTS_DIR


def load_classification_variant(name: str) -> ClassificationVariant:
    """Load variant config from eval/variants/{name}.yaml."""
    if name == "baseline":
        return ClassificationVariant(name="baseline")

    path = _variants_dir() / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Variant config not found: {path}. "
            f"Copy proposed.example.yaml to {name}.yaml and edit."
        )

    raw = yaml.safe_load(path.read_text()) or {}
    system_prompt: str | None = None
    prompt_file = raw.get("system_prompt_file")
    if prompt_file:
        prompt_path = path.parent / prompt_file
        if not prompt_path.exists():
            raise FileNotFoundError(f"system_prompt_file not found: {prompt_path}")
        system_prompt = prompt_path.read_text()

    return ClassificationVariant(
        name=name,
        selection_model=raw.get("selection_model"),
        system_prompt=system_prompt,
    )
