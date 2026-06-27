"""Write BUILD_INFO.json from the current git HEAD commit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    built_at = subprocess.check_output(["git", "log", "-1", "--format=%cI"], text=True).strip()
    commit_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    commit_message = subprocess.check_output(["git", "log", "-1", "--format=%s"], text=True).strip()[:200]
    payload = {
        "built_at": built_at,
        "commit_sha": commit_sha,
        "commit_message": commit_message,
    }

    path = Path("BUILD_INFO.json")
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if existing == payload:
        print("BUILD_INFO.json already up to date.")
        return 0

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Updated BUILD_INFO.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
