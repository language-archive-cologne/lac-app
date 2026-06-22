import environ


def configure_database_connections(
    database: dict,
    env: environ.Env,
    *,
    conn_max_age_default: int = 60,
) -> None:
    database["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=conn_max_age_default)
    database["DISABLE_SERVER_SIDE_CURSORS"] = env.bool(
        "DISABLE_SERVER_SIDE_CURSORS",
        default=False,
    )
