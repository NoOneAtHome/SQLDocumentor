"""Config loading: YAML -> ${ENV} interpolation -> validated AppConfig."""

from pathlib import Path

import pytest

from sqldoc.config.loader import ConfigError, load_config

MINIMAL = """
version: 1
connections:
  - name: local
    host: localhost
    auth: {{ mode: sql, username: sa, password: "{password}" }}
    databases:
      - {{ name: AdventureWorks2022, schemas: [Sales, HumanResources] }}
"""


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "sqldoc.yaml"
    p.write_text(text)
    return p


def test_interpolates_env_var_into_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("MSSQL_PW", "s3cret")
    cfg = load_config(write(tmp_path, MINIMAL.format(password="${MSSQL_PW}")))

    conn = cfg.connections[0]
    assert conn.auth.password is not None
    assert conn.auth.password.get_secret_value() == "s3cret"
    # secrets never leak through repr/str
    assert "s3cret" not in repr(cfg)
    assert "s3cret" not in str(cfg)


def test_missing_env_var_names_key_path_and_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_PW", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, MINIMAL.format(password="${NOPE_PW}")))
    assert "NOPE_PW" in str(exc.value)
    assert "connections[0].auth.password" in str(exc.value)


def test_defaults(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL.format(password="plain")))
    conn = cfg.connections[0]
    assert conn.port == 1433
    assert conn.encrypt is True
    assert conn.trust_server_certificate is False
    assert conn.driver == "auto"
    assert cfg.scan.cascade_foreign_keys is True
    assert cfg.scan.include_triggers_of_cascaded_tables is True
    assert cfg.scan.collect_stats is True
    assert cfg.scan.parse_lineage is True
    # sqlite path defaults next to the config file
    assert cfg.storage.sqlite_path == (tmp_path / "sqldoc.sqlite")


def test_relative_sqlite_path_resolves_against_config_dir(tmp_path):
    text = MINIMAL.format(password="plain") + "storage: { sqlite_path: data/x.sqlite }\n"
    cfg = load_config(write(tmp_path, text))
    assert cfg.storage.sqlite_path == tmp_path / "data" / "x.sqlite"


def test_sql_auth_requires_username_and_password(tmp_path):
    text = MINIMAL.format(password="plain").replace("username: sa, ", "")
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, text))
    assert "username" in str(exc.value)


def test_integrated_auth_needs_no_credentials(tmp_path):
    text = MINIMAL.format(password="x").replace(
        'auth: { mode: sql, username: sa, password: "x" }', "auth: { mode: integrated }"
    )
    cfg = load_config(write(tmp_path, text))
    assert cfg.connections[0].auth.mode == "integrated"
    assert cfg.connections[0].auth.username is None
    assert cfg.connections[0].auth.password is None


def test_duplicate_connection_names_rejected(tmp_path):
    text = MINIMAL.format(password="plain")
    text += """
  - name: local
    host: other
    auth: { mode: integrated }
    databases:
      - { name: X, schemas: [dbo] }
"""
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, text))
    assert "local" in str(exc.value)


def test_database_needs_at_least_one_schema(tmp_path):
    text = MINIMAL.format(password="plain").replace(
        "schemas: [Sales, HumanResources]", "schemas: []"
    )
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


def test_is_selected_is_case_insensitive(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL.format(password="plain")))
    conn = cfg.connections[0]
    assert conn.is_selected("adventureworks2022", "SALES")
    assert conn.is_selected("AdventureWorks2022", "humanresources")
    assert not conn.is_selected("AdventureWorks2022", "Person")
    assert not conn.is_selected("OtherDb", "Sales")
    assert conn.is_configured_database("ADVENTUREWORKS2022")
    assert not conn.is_configured_database("master")


def test_get_connection_by_name_and_unknown_name(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL.format(password="plain")))
    assert cfg.connection("local").host == "localhost"
    with pytest.raises(ConfigError):
        cfg.connection("missing")


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_dotenv_next_to_config_feeds_interpolation(tmp_path, monkeypatch):
    monkeypatch.delenv("FROM_DOTENV", raising=False)
    (tmp_path / ".env").write_text("FROM_DOTENV=dotenv-secret\n")
    cfg = load_config(write(tmp_path, MINIMAL.format(password="${FROM_DOTENV}")))
    assert cfg.connections[0].auth.password.get_secret_value() == "dotenv-secret"


def test_process_env_wins_over_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("PW", "from-process")
    (tmp_path / ".env").write_text("PW=from-dotenv\n")
    cfg = load_config(write(tmp_path, MINIMAL.format(password="${PW}")))
    assert cfg.connections[0].auth.password.get_secret_value() == "from-process"
