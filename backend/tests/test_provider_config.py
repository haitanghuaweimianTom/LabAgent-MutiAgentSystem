"""Tests for provider_config.py — CC Switch sync and detection."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.provider_config import (
    _read_config,
    _write_config,
    detect_ccswitch_providers,
    detect_ccswitch_change,
    sync_ccswitch_to_local,
    get_ccswitch_status,
    CCSWITCH_DB,
    _last_ccswitch_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ccswitch_db(db_path: Path, rows: list) -> None:
    """Create a ccswitch SQLite DB with the given provider rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE providers ("
        "id TEXT PRIMARY KEY, name TEXT, app_type TEXT, "
        "settings_config TEXT, is_current INTEGER)"
    )
    for r in rows:
        conn.execute(
            "INSERT INTO providers (id, name, app_type, settings_config, is_current) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                r["id"],
                r.get("name", ""),
                r.get("app_type", "claude"),
                json.dumps(r.get("settings_config", {})),
                1 if r.get("is_current") else 0,
            ),
        )
    conn.commit()
    conn.close()


def _make_agent_configs(agent_path: Path, data: dict) -> None:
    """Write agent_configs.json for isolation tests."""
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. detect_ccswitch_not_installed
# ---------------------------------------------------------------------------

def test_detect_ccswitch_not_installed(tmp_path: Path, monkeypatch):
    """When CCSWITCH_DB doesn't exist, detect_ccswitch_providers returns []."""
    fake_db = tmp_path / "no-such-db" / "cc-switch.db"
    monkeypatch.setattr(
        "app.core.provider_config.CCSWITCH_DB", fake_db
    )
    assert detect_ccswitch_providers() == []


# ---------------------------------------------------------------------------
# 2. detect_ccswitch_db_locked
# ---------------------------------------------------------------------------

def test_detect_ccswitch_db_locked(tmp_path: Path, monkeypatch):
    """When sqlite3.OperationalError occurs, returns [] gracefully."""
    fake_db = tmp_path / "cc-switch.db"
    # Create a DB but corrupt it so sqlite raises OperationalError
    fake_db.write_text("NOT A VALID DB", encoding="utf-8")
    monkeypatch.setattr("app.core.provider_config.CCSWITCH_DB", fake_db)
    assert detect_ccswitch_providers() == []


# ---------------------------------------------------------------------------
# 3. sync_ccswitch_adds_new_provider
# ---------------------------------------------------------------------------

def test_sync_ccswitch_adds_new_provider(tmp_path: Path, monkeypatch):
    """Mock detect_ccswitch_providers returning a new provider; verify it's added."""
    custom_providers_json = tmp_path / "custom_providers.json"
    monkeypatch.setattr(
        "app.core.provider_config.CONFIG_FILE", custom_providers_json
    )
    # Ensure clean state
    custom_providers_json.write_text(
        json.dumps({"providers": [], "default_provider": None, "_version": 2}),
        encoding="utf-8",
    )

    mock_provider = {
        "id": "cs-new-1",
        "name": "New CCSwitch Provider",
        "type": "anthropic",
        "api_key": "sk-new",
        "api_host": "https://api.new.com",
        "models": [{"name": "claude-sonnet", "enabled": True}],
        "meta": {"api_format": "anthropic"},
        "_ccswitch_current": False,
    }

    with patch(
        "app.core.provider_config.detect_ccswitch_providers",
        return_value=[mock_provider],
    ):
        result = sync_ccswitch_to_local(force=True)

    assert result["added"] == 1
    assert result["updated"] == 0
    assert result["synced"] == 1

    config = _read_config()
    ids = [p["id"] for p in config.get("providers", [])]
    assert "cs-new-1" in ids

    new_p = next(p for p in config["providers"] if p["id"] == "cs-new-1")
    assert new_p["api_key"] == "sk-new"
    assert new_p["api_host"] == "https://api.new.com"


# ---------------------------------------------------------------------------
# 4. sync_ccswitch_updates_existing
# ---------------------------------------------------------------------------

def test_sync_ccswitch_updates_existing(tmp_path: Path, monkeypatch):
    """Mock returning same id but different api_key; verify updated."""
    custom_providers_json = tmp_path / "custom_providers.json"
    monkeypatch.setattr(
        "app.core.provider_config.CONFIG_FILE", custom_providers_json
    )
    initial = {
        "providers": [
            {
                "id": "cs-existing",
                "name": "Existing",
                "type": "anthropic",
                "category": "custom",
                "meta": {"api_format": "anthropic"},
                "api_key": "sk-old",
                "api_host": "https://api.old.com",
                "models": [],
                "enabled": True,
                "icon": "Claude",
                "icon_color": "#d97706",
                "notes": "",
                "created_at": 1,
                "updated_at": 1,
                "_version": 2,
            }
        ],
        "default_provider": None,
        "_version": 2,
    }
    custom_providers_json.write_text(json.dumps(initial), encoding="utf-8")

    mock_provider = {
        "id": "cs-existing",
        "name": "Existing",
        "type": "anthropic",
        "api_key": "sk-new",
        "api_host": "https://api.new.com",
        "models": [{"name": "claude-opus", "enabled": True}],
        "meta": {"api_format": "anthropic"},
        "_ccswitch_current": False,
    }

    with patch(
        "app.core.provider_config.detect_ccswitch_providers",
        return_value=[mock_provider],
    ):
        result = sync_ccswitch_to_local(force=True)

    assert result["added"] == 0
    assert result["updated"] == 1
    assert result["synced"] == 1

    config = _read_config()
    p = next(x for x in config["providers"] if x["id"] == "cs-existing")
    assert p["api_key"] == "sk-new"
    assert p["api_host"] == "https://api.new.com"
    assert p["models"] == [{"name": "claude-opus", "enabled": True}]


# ---------------------------------------------------------------------------
# 5. sync_ccswitch_sets_default
# ---------------------------------------------------------------------------

def test_sync_ccswitch_sets_default(tmp_path: Path, monkeypatch):
    """Mock with _ccswitch_current=True; verify default_provider set."""
    custom_providers_json = tmp_path / "custom_providers.json"
    monkeypatch.setattr(
        "app.core.provider_config.CONFIG_FILE", custom_providers_json
    )
    custom_providers_json.write_text(
        json.dumps({"providers": [], "default_provider": None, "_version": 2}),
        encoding="utf-8",
    )

    mock_provider = {
        "id": "cs-default",
        "name": "Default Provider",
        "type": "anthropic",
        "api_key": "sk-d",
        "api_host": "https://api.d.com",
        "models": [{"name": "claude-sonnet", "enabled": True}],
        "meta": {"api_format": "anthropic"},
        "_ccswitch_current": True,
    }

    with patch(
        "app.core.provider_config.detect_ccswitch_providers",
        return_value=[mock_provider],
    ):
        result = sync_ccswitch_to_local(force=True)

    assert result["default"] == "cs-default"
    config = _read_config()
    assert config.get("default_provider") == "cs-default"


# ---------------------------------------------------------------------------
# 6. sync_ccswitch_idempotent
# ---------------------------------------------------------------------------

def test_sync_ccswitch_idempotent(tmp_path: Path, monkeypatch):
    """Call twice with same data; second call should be unchanged."""
    custom_providers_json = tmp_path / "custom_providers.json"
    monkeypatch.setattr(
        "app.core.provider_config.CONFIG_FILE", custom_providers_json
    )
    custom_providers_json.write_text(
        json.dumps({"providers": [], "default_provider": None, "_version": 2}),
        encoding="utf-8",
    )

    mock_provider = {
        "id": "cs-idem",
        "name": "Idem",
        "type": "anthropic",
        "api_key": "sk-i",
        "api_host": "https://api.i.com",
        "models": [{"name": "claude-sonnet", "enabled": True}],
        "meta": {"api_format": "anthropic"},
        "_ccswitch_current": False,
    }

    with patch(
        "app.core.provider_config.detect_ccswitch_providers",
        return_value=[mock_provider],
    ):
        # First call — adds (force=True bypasses change detection)
        r1 = sync_ccswitch_to_local(force=True)
        assert r1["synced"] == 1

        # Seed the change-detection cache so the second call sees no diff.
        with patch(
            "app.core.provider_config.detect_ccswitch_providers",
            return_value=[mock_provider],
        ):
            detect_ccswitch_change()

        # Second call — with force=False, change detection runs.
        # Because the mock still returns the same provider, detect_ccswitch_change
        # compares against the cached _last_ccswitch_state. Since nothing changed,
        # it should return None and sync should report unchanged.
        r2 = sync_ccswitch_to_local(force=False)
        assert r2.get("unchanged") is True
        assert r2["synced"] == 0


# ---------------------------------------------------------------------------
# 7. sync_ccswitch_preserves_agent_overrides
# ---------------------------------------------------------------------------

def test_sync_ccswitch_preserves_agent_overrides(tmp_path: Path, monkeypatch):
    """Verify agent_model_map in agent_configs.json is untouched after sync."""
    custom_providers_json = tmp_path / "custom_providers.json"
    agent_configs_json = tmp_path / "agent_configs.json"

    monkeypatch.setattr(
        "app.core.provider_config.CONFIG_FILE", custom_providers_json
    )

    custom_providers_json.write_text(
        json.dumps({"providers": [], "default_provider": None, "_version": 2}),
        encoding="utf-8",
    )

    agent_data = {
        "agents": {
            "writer": {
                "provider": "custom-writer",
                "model": "gpt-4o",
            },
            "reviewer": {
                "provider": "custom-reviewer",
                "model": "claude-sonnet",
            },
        },
        "agent_model_map": {
            "writer": {"provider": "custom-writer", "model": "gpt-4o"},
            "reviewer": {"provider": "custom-reviewer", "model": "claude-sonnet"},
        },
    }
    _make_agent_configs(agent_configs_json, agent_data)

    mock_provider = {
        "id": "cs-agent",
        "name": "Agent Sync",
        "type": "anthropic",
        "api_key": "sk-a",
        "api_host": "https://api.a.com",
        "models": [{"name": "claude-sonnet", "enabled": True}],
        "meta": {"api_format": "anthropic"},
        "_ccswitch_current": False,
    }

    with patch(
        "app.core.provider_config.detect_ccswitch_providers",
        return_value=[mock_provider],
    ):
        sync_ccswitch_to_local(force=True)

    # agent_configs.json should remain exactly as it was
    persisted = json.loads(agent_configs_json.read_text("utf-8"))
    assert persisted.get("agent_model_map") == agent_data["agent_model_map"]
    assert persisted["agents"]["writer"]["provider"] == "custom-writer"


# ---------------------------------------------------------------------------
# 8. get_ccswitch_status_not_installed
# ---------------------------------------------------------------------------

def test_get_ccswitch_status_not_installed(tmp_path: Path, monkeypatch):
    """Verify installed=False when no DB."""
    fake_db = tmp_path / "missing" / "cc-switch.db"
    monkeypatch.setattr("app.core.provider_config.CCSWITCH_DB", fake_db)
    status = get_ccswitch_status()
    assert status["installed"] is False
    assert status["connected"] is False
    assert status["providers_count"] == 0


# ---------------------------------------------------------------------------
# 9. get_ccswitch_status_installed
# ---------------------------------------------------------------------------

def test_get_ccswitch_status_installed(tmp_path: Path, monkeypatch):
    """Mock detect_ccswitch_providers; verify status fields."""
    fake_db = tmp_path / "cc-switch.db"
    _make_ccswitch_db(
        fake_db,
        [
            {
                "id": "cs-1",
                "name": "Provider One",
                "app_type": "claude",
                "settings_config": {
                    "env": {
                        "ANTHROPIC_BASE_URL": "https://api.one.com",
                        "ANTHROPIC_AUTH_TOKEN": "sk-one",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet",
                    }
                },
                "is_current": True,
            },
            {
                "id": "cs-2",
                "name": "Provider Two",
                "app_type": "claude",
                "settings_config": {
                    "env": {
                        "ANTHROPIC_BASE_URL": "https://api.two.com",
                        "ANTHROPIC_AUTH_TOKEN": "sk-two",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-opus",
                    }
                },
                "is_current": False,
            },
        ],
    )
    monkeypatch.setattr("app.core.provider_config.CCSWITCH_DB", fake_db)
    # Reset cache so detect doesn't short-circuit
    monkeypatch.setattr(
        "app.core.provider_config._last_ccswitch_state", {}
    )

    status = get_ccswitch_status()
    assert status["installed"] is True
    assert status["connected"] is True
    assert status["providers_count"] == 2
    assert status["current_provider"] == "Provider One"
    assert status["db_path"] == str(fake_db)
