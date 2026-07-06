#!/usr/bin/env python3
"""Hash plaintext admin passwords in a VPS .env file (staging/production)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import bcrypt

BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
PASSWORD_KEYS = ("ADMIN_PASSWORD", "STAGING_ADMIN_PASSWORD")


def is_bcrypt(value: str) -> bool:
    return value.startswith(BCRYPT_PREFIXES)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upgrade_env_file(path: Path) -> int:
    if not path.is_file():
        return 0

    changed = 0
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if not match:
            out.append(line)
            continue

        key, raw = match.group(1), match.group(2)
        if key not in PASSWORD_KEYS:
            out.append(line)
            continue

        value = unquote(raw)
        if not value or is_bcrypt(value):
            out.append(line)
            continue

        out.append(f"{key}={hash_password(value)}")
        changed += 1
        print(f"   Hashed plaintext {key} in {path}")

    if changed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")

    return changed


def main() -> int:
    env_path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    changed = upgrade_env_file(env_path)
    print(f"Updated {changed} password entr{'y' if changed == 1 else 'ies'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
