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


@dataclass
class ExtractionVariant:
    name: str
    extraction_model: str | None = None
    system_prompt: str | None = None


def _load_variant_yaml(name: str) -> tuple[Path, dict]:
    path = _variants_dir() / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Variant config not found: {path}. "
            f"Copy proposed.example.yaml to {name}.yaml and edit."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    return path, raw


def _load_system_prompt(path: Path, raw: dict) -> str | None:
    prompt_file = raw.get("system_prompt_file")
    if not prompt_file:
        return None
    prompt_path = path.parent / prompt_file
    if not prompt_path.exists():
        raise FileNotFoundError(f"system_prompt_file not found: {prompt_path}")
    return prompt_path.read_text()


def load_classification_variant(name: str) -> ClassificationVariant:
    """Load variant config from eval/variants/{name}.yaml."""
    if name == "baseline":
        return ClassificationVariant(name="baseline")

    path, raw = _load_variant_yaml(name)
    return ClassificationVariant(
        name=name,
        selection_model=raw.get("selection_model"),
        system_prompt=_load_system_prompt(path, raw),
    )


def load_extraction_variant(name: str) -> ExtractionVariant:
    """Load extraction variant config from eval/variants/{name}.yaml."""
    if name == "baseline":
        return ExtractionVariant(name="baseline")

    path, raw = _load_variant_yaml(name)
    return ExtractionVariant(
        name=name,
        extraction_model=raw.get("extraction_model"),
        system_prompt=_load_system_prompt(path, raw),
    )
