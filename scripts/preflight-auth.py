#!/usr/bin/env python3
"""Validate auth config using a mounted deploy .env file."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def load_deploy_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        os.environ[key] = value.replace("$$", "$")


def main() -> int:
    env_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/run/deploy.env")
    load_deploy_env(env_path)
    os.environ.setdefault("ENVIRONMENT", "production")
    os.environ.setdefault("ENABLE_AUTH", "true")

    from app.auth import validate_auth_config

    validate_auth_config()
    print("Auth config OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
