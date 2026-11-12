"""Configuration, path, portable-mode and settings tests."""

from __future__ import annotations

from services import config


def test_windows_paths(monkeypatch, workdir):
    monkeypatch.setattr(config, "platform_name", lambda: "windows")
    monkeypatch.setenv("APPDATA", str(workdir / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(workdir / "local"))
    monkeypatch.delenv("KICAD_LIB_GEN_CONFIG_DIR", raising=False)
    monkeypatch.delenv("KICAD_LIB_GEN_LOG_DIR", raising=False)
    assert config.config_dir(portable=False) == workdir / "roaming" / "KiCadLibGen"
    assert config.log_dir(portable=False) == workdir / "local" / "KiCadLibGen" / "logs"
    assert config.settings_path(False).name == "settings.json"
    assert config.default_token_path(False).name == "token.json"


def test_linux_paths(monkeypatch, workdir):
    monkeypatch.setattr(config, "platform_name", lambda: "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(workdir / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(workdir / "state"))
    monkeypatch.delenv("KICAD_LIB_GEN_CONFIG_DIR", raising=False)
    monkeypatch.delenv("KICAD_LIB_GEN_LOG_DIR", raising=False)
    assert config.config_dir(portable=False) == workdir / "cfg" / "kicad-lib-gen"
    assert config.log_dir(portable=False) == workdir / "state" / "kicad-lib-gen" / "logs"


def test_env_overrides(monkeypatch, workdir):
    monkeypatch.setenv("KICAD_LIB_GEN_CONFIG_DIR", str(workdir / "override"))
    monkeypatch.setenv("KICAD_LIB_GEN_LOG_DIR", str(workdir / "logs"))
    assert config.config_dir(False) == workdir / "override"
    assert config.log_dir(False) == workdir / "logs"


def test_portable_mode(monkeypatch, workdir):
    monkeypatch.setattr(config, "app_dir", lambda: workdir)
    monkeypatch.delenv("KICAD_LIB_GEN_PORTABLE", raising=False)
    assert config.resolve_portable(None) is False
    (workdir / "portable.txt").write_text("", encoding="utf-8")
    assert config.resolve_portable(None) is True
    assert config.config_dir(None) == workdir / "data"
    assert config.log_dir(None) == workdir / "data" / "logs"


def test_sync_folder_detection(workdir):
    assert config.sync_folder_name("C:/Users/me/OneDrive - Work/x.db") == "OneDrive"
    assert config.sync_folder_name("C:/Users/me/Dropbox/x.db") == "Dropbox"
    assert config.sync_folder_name("C:/Users/me/Local/x.db") is None


def test_settings_roundtrip(workdir):
    path = workdir / "settings.json"
    settings = config.Settings(
        database_path=str(workdir / "components.db"),
        token_path=str(workdir / "token.json"),
        search_limit=50,
        http_timeout=45,
        batch_delay_ms=500,
        log_level="DEBUG",
        recent_databases=["a", "b"],
    )
    settings.source_path = path
    settings.save()
    loaded = config.Settings.load(path=path)
    assert loaded.database_path == settings.database_path
    assert loaded.search_limit == 50
    assert loaded.http_timeout == 45
    assert loaded.batch_delay_ms == 500
    assert loaded.log_level == "DEBUG"
    assert loaded.recent_databases == ["a", "b"]


def test_settings_missing_and_corrupt_fallback(workdir):
    path = workdir / "settings.json"
    loaded = config.Settings.load(path=path)
    assert loaded.search_limit == config.DEFAULT_SEARCH_LIMIT
    path.write_text("{not json", encoding="utf-8")
    loaded = config.Settings.load(path=path)
    assert loaded.search_limit == config.DEFAULT_SEARCH_LIMIT
    assert loaded.portable is False


def test_settings_validation(workdir):
    settings = config.Settings(search_limit=37, http_timeout=1,
                               batch_delay_ms=99999, log_level="NOPE")
    assert settings.search_limit in config.SEARCH_LIMITS
    assert settings.http_timeout == 5
    assert settings.batch_delay_ms == 10000
    assert settings.log_level == "INFO"


def test_recent_databases(workdir):
    settings = config.Settings()
    for index in range(12):
        settings.add_recent(workdir / f"db{index}.db")
    assert len(settings.recent_databases) == config.MAX_RECENT_DATABASES
    assert settings.recent_databases[0].endswith("db11.db")
    settings.add_recent(workdir / "db5.db")
    assert settings.recent_databases[0].endswith("db5.db")
    assert len(settings.recent_databases) == config.MAX_RECENT_DATABASES


def test_legacy_token_candidates(monkeypatch, workdir):
    monkeypatch.setattr(config, "app_dir", lambda: workdir)
    monkeypatch.chdir(workdir)
    candidates = config.legacy_token_candidates()
    assert workdir / ".token" in candidates
    assert len(candidates) == len({str(item) for item in candidates})
