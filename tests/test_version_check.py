from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.version_check import (
    VersionInfo,
    check_for_updates,
    compare_versions,
    fetch_remote_version,
    format_version_datetime,
    get_local_version,
    parse_version_datetime,
    run_update_script,
)


def test_compare_versions_orders_by_datetime() -> None:
    older = VersionInfo(built_at="2026-06-27T10:00:00+07:00")
    newer = VersionInfo(built_at="2026-06-27T12:00:00+07:00")
    assert compare_versions(older, newer) < 0
    assert compare_versions(newer, older) > 0
    assert compare_versions(newer, newer) == 0


def test_format_version_datetime_wib() -> None:
    formatted = format_version_datetime("2026-06-27T14:54:56+07:00")
    assert "Jun 2026" in formatted
    assert "WIB" in formatted


def test_get_local_version_reads_build_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_info = tmp_path / "BUILD_INFO.json"
    build_info.write_text(
        json.dumps(
            {
                "built_at": "2026-06-27T14:54:56+07:00",
                "commit_sha": "abc1234",
                "commit_message": "Test build",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.version_check.BUILD_INFO_PATH", build_info)
    version = get_local_version()
    assert version is not None
    assert version.commit_sha == "abc1234"
    assert version.built_at.endswith("+07:00")


def test_fetch_remote_version_parses_github_payload() -> None:
    payload = {
        "sha": "deadbeef1234567890",
        "commit": {
            "committer": {"date": "2026-06-27T08:00:00Z"},
            "message": "Remote update",
        },
    }
    response = MagicMock()
    response.__enter__.return_value = response
    response.read = MagicMock(return_value=json.dumps(payload).encode("utf-8"))

    with patch("src.version_check.urllib.request.urlopen", return_value=response):
        version = fetch_remote_version()

    assert version is not None
    assert version.commit_sha == "deadbee"
    assert version.commit_message == "Remote update"


def test_check_for_updates_detects_newer_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    local = VersionInfo(built_at="2026-06-27T10:00:00+07:00", source="local")
    remote = VersionInfo(built_at="2026-06-27T12:00:00+07:00", source="remote")
    monkeypatch.setattr("src.version_check.get_local_version", lambda: local)
    monkeypatch.setattr("src.version_check.fetch_remote_version", lambda: remote)

    result = check_for_updates(force=True)
    assert result.update_available is True
    assert result.remote is not None


def test_check_for_updates_handles_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    local = VersionInfo(built_at="2026-06-27T10:00:00+07:00", source="local")
    monkeypatch.setattr("src.version_check.get_local_version", lambda: local)
    monkeypatch.setattr("src.version_check.fetch_remote_version", lambda: None)

    result = check_for_updates(force=True)
    assert result.update_available is False
    assert "GitHub" in result.error


def test_run_update_script_returns_output(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "Update completed."
    completed.stderr = ""
    monkeypatch.setattr("src.version_check.platform.system", lambda: "Windows")
    monkeypatch.setattr("src.version_check.subprocess.run", lambda *args, **kwargs: completed)

    result = run_update_script()
    assert result.success is True
    assert "Update completed" in result.output


def test_parse_version_datetime_accepts_zulu() -> None:
    parsed = parse_version_datetime("2026-06-27T08:00:00Z")
    assert parsed.tzinfo is not None
