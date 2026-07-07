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
    normalized = normalize_docker_value(unquote(value))
    return normalized.startswith(BCRYPT_PREFIXES)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def normalize_docker_value(value: str) -> str:
    """Undo Docker Compose .env escaping before hashing or validation."""
    return unquote(value).replace("$$", "$")


def escape_for_docker_compose(value: str) -> str:
    return normalize_docker_value(value).replace("$", "$$")


def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def format_env_value(value: str) -> str:
    return escape_for_docker_compose(value)


def upgrade_password_value(raw: str) -> tuple[str, bool]:
    normalized = normalize_docker_value(raw)
    if not normalized:
        return raw, False
    if is_bcrypt(normalized):
        formatted = format_env_value(normalized)
        return formatted, formatted != raw.strip()
    hashed = format_env_value(hash_password(normalized))
    return hashed, True


def upgrade_admin_users(raw: str) -> tuple[str, int]:
    changed = 0
    pairs: list[str] = []
    for chunk in normalize_docker_value(raw).split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        user, pwd_raw = chunk.split(":", 1)
        normalized = normalize_docker_value(pwd_raw)
        if not normalized:
            pairs.append(f"{user.strip()}:{pwd_raw}")
            continue
        if is_bcrypt(normalized):
            escaped = format_env_value(normalized)
            if escaped != pwd_raw.strip():
                changed += 1
            pairs.append(f"{user.strip()}:{escaped}")
            continue
        pairs.append(f"{user.strip()}:{format_env_value(hash_password(normalized))}")
        changed += 1
    if not pairs:
        return raw, 0
    return ",".join(pairs), changed


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
        if key == "ADMIN_USERS":
            upgraded, count = upgrade_admin_users(raw)
            out.append(f"{key}={upgraded}")
            changed += count
            if count:
                print(f"   Updated ADMIN_USERS in {path}")
            continue

        if key not in PASSWORD_KEYS:
            out.append(line)
            continue

        upgraded, did_change = upgrade_password_value(raw)
        out.append(f"{key}={upgraded}")
        if did_change:
            changed += 1
            print(f"   Updated {key} in {path}")

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
