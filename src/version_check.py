from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import platform
import subprocess
from pathlib import Path
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from src.config import GITHUB_API_URL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_INFO_PATH = PROJECT_ROOT / "BUILD_INFO.json"
UPDATE_CACHE_TTL_SECONDS = 6 * 60 * 60
WIB = ZoneInfo("Asia/Jakarta")


@dataclass(frozen=True)
class VersionInfo:
    built_at: str
    commit_sha: str = ""
    commit_message: str = ""
    source: str = "unknown"

    @property
    def display(self) -> str:
        return format_version_datetime(self.built_at)

    @property
    def sort_key(self) -> datetime:
        return parse_version_datetime(self.built_at)


@dataclass(frozen=True)
class UpdateCheckResult:
    local: VersionInfo | None
    remote: VersionInfo | None
    update_available: bool
    error: str = ""


@dataclass(frozen=True)
class UpdateRunResult:
    success: bool
    return_code: int
    output: str
    error: str = ""


def get_local_version() -> VersionInfo | None:
    if BUILD_INFO_PATH.exists():
        try:
            payload = json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8"))
            built_at = str(payload.get("built_at", "")).strip()
            if built_at:
                return VersionInfo(
                    built_at=built_at,
                    commit_sha=str(payload.get("commit_sha", "")).strip(),
                    commit_message=str(payload.get("commit_message", "")).strip(),
                    source="BUILD_INFO.json",
                )
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    git_dir = PROJECT_ROOT / ".git"
    if git_dir.exists():
        try:
            completed = subprocess.run(
                ["git", "log", "-1", "--format=%cI|%h|%s"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            parts = completed.stdout.strip().split("|", 2)
            if parts and parts[0]:
                return VersionInfo(
                    built_at=parts[0],
                    commit_sha=parts[1] if len(parts) > 1 else "",
                    commit_message=parts[2] if len(parts) > 2 else "",
                    source="git",
                )
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def fetch_remote_version() -> VersionInfo | None:
    request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "CasemixFileAuditor",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    commit = payload.get("commit") if isinstance(payload, dict) else None
    if not isinstance(commit, dict):
        return None

    built_at = ""
    committer = commit.get("committer")
    if isinstance(committer, dict):
        built_at = str(committer.get("date", "")).strip()
    if not built_at:
        author = commit.get("author")
        if isinstance(author, dict):
            built_at = str(author.get("date", "")).strip()
    if not built_at:
        return None

    sha = str(payload.get("sha", ""))[:7]
    message = ""
    if isinstance(commit.get("message"), str):
        message = commit["message"].splitlines()[0][:200]
    return VersionInfo(
        built_at=built_at,
        commit_sha=sha,
        commit_message=message,
        source="github_api",
    )


def compare_versions(left: VersionInfo | None, right: VersionInfo | None) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return -1
    if right is None:
        return 1
    left_dt = left.sort_key
    right_dt = right.sort_key
    if left_dt < right_dt:
        return -1
    if left_dt > right_dt:
        return 1
    return 0


def check_for_updates(*, force: bool = False, cached: UpdateCheckResult | None = None) -> UpdateCheckResult:
    if not force and cached is not None:
        return cached

    local = get_local_version()
    remote = fetch_remote_version()
    if remote is None:
        return UpdateCheckResult(
            local=local,
            remote=None,
            update_available=False,
            error="Tidak dapat memeriksa versi terbaru dari GitHub.",
        )

    update_available = compare_versions(local, remote) < 0
    return UpdateCheckResult(
        local=local,
        remote=remote,
        update_available=update_available,
    )


def run_update_script() -> UpdateRunResult:
    if platform.system().lower().startswith("win"):
        command = ["cmd.exe", "/c", str(PROJECT_ROOT / "update.bat")]
    else:
        command = ["bash", str(PROJECT_ROOT / "scripts" / "update.sh")]

    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return UpdateRunResult(
            success=False,
            return_code=1,
            output="",
            error=str(exc),
        )

    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
    return UpdateRunResult(
        success=completed.returncode == 0,
        return_code=completed.returncode,
        output=output,
        error="" if completed.returncode == 0 else "Pembaruan gagal.",
    )


def parse_version_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=WIB)
    return parsed.astimezone(WIB)


def format_version_datetime(value: str) -> str:
    try:
        parsed = parse_version_datetime(value)
    except ValueError:
        return value
    return parsed.strftime("%d %b %Y %H:%M WIB")
