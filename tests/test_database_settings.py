import environ

from config.settings.database import configure_database_connections


def test_configure_database_connections_defaults_to_persistent_connections(monkeypatch):
    monkeypatch.delenv("CONN_MAX_AGE", raising=False)
    monkeypatch.delenv("DISABLE_SERVER_SIDE_CURSORS", raising=False)
    database = {}

    configure_database_connections(database, environ.Env())

    assert database["CONN_MAX_AGE"] == 60
    assert database["DISABLE_SERVER_SIDE_CURSORS"] is False


def test_configure_database_connections_supports_transaction_pooling(monkeypatch):
    monkeypatch.setenv("CONN_MAX_AGE", "0")
    monkeypatch.setenv("DISABLE_SERVER_SIDE_CURSORS", "true")
    database = {}

    configure_database_connections(database, environ.Env())

    assert database["CONN_MAX_AGE"] == 0
    assert database["DISABLE_SERVER_SIDE_CURSORS"] is True


def test_configure_database_connections_preserves_local_default(monkeypatch):
    monkeypatch.delenv("CONN_MAX_AGE", raising=False)
    monkeypatch.delenv("DISABLE_SERVER_SIDE_CURSORS", raising=False)
    database = {}

    configure_database_connections(
        database,
        environ.Env(),
        conn_max_age_default=0,
    )

    assert database["CONN_MAX_AGE"] == 0
    assert database["DISABLE_SERVER_SIDE_CURSORS"] is False
