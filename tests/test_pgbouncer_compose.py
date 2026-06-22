from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("compose_file", "env_dir", "host_port", "image_name"),
    [
        ("docker-compose.local.yml", ".local", "6431", "lacos_local_pgbouncer"),
        ("docker-compose.dev.yml", ".dev", "6433", "lacos_dev_pgbouncer"),
        ("docker-compose.production.yml", ".production", "6434", "lacos_production_pgbouncer"),
    ],
)
def test_app_services_route_through_pgbouncer_transaction_pool(
    compose_file: str,
    env_dir: str,
    host_port: str,
    image_name: str,
):
    compose_path = _compose_path(compose_file)

    for service_name in ("django", "huey"):
        env = _service_environment(compose_path, service_name)

        assert env["POSTGRES_HOST"] == "pgbouncer"
        assert env["POSTGRES_PORT"] == "6432"
        assert env["CONN_MAX_AGE"] == "0"
        assert env["DISABLE_SERVER_SIDE_CURSORS"] == "true"

    pgbouncer_env = _service_environment(compose_path, "pgbouncer")
    pgbouncer_block = "\n".join(_service_block(compose_path, "pgbouncer"))
    postgres_block = "\n".join(_service_block(compose_path, "postgres"))

    assert pgbouncer_env["PGBOUNCER_SERVER_HOST"] == "postgres"
    assert pgbouncer_env["PGBOUNCER_SERVER_PORT"] == "5432"
    assert pgbouncer_env["PGBOUNCER_POOL_MODE"] == "transaction"
    assert pgbouncer_env["PGBOUNCER_DEFAULT_POOL_SIZE"] == "30"
    assert pgbouncer_env["PGBOUNCER_RESERVE_POOL_SIZE"] == "10"
    assert f"image: {image_name}" in pgbouncer_block
    assert "dockerfile: ./compose/production/pgbouncer/Dockerfile" in pgbouncer_block
    assert f"- ./.envs/{env_dir}/.postgres" in pgbouncer_block
    assert f"127.0.0.1:{host_port}:6432" in pgbouncer_block
    assert "POSTGRES_HOST: pgbouncer" not in postgres_block
    assert "POSTGRES_PORT: \"6432\"" not in postgres_block


@pytest.mark.parametrize(
    "compose_file",
    ["docker-compose.local.yml", "docker-compose.dev.yml", "docker-compose.production.yml"],
)
def test_pgbouncer_compose_does_not_special_case_oai_routes(compose_file: str):
    assert "/oai/" not in _compose_path(compose_file).read_text()


def test_pgbouncer_keeps_production_logs_operational_but_not_per_connection():
    template = (
        Path(__file__).resolve().parents[1]
        / "compose"
        / "production"
        / "pgbouncer"
        / "pgbouncer.ini.template"
    ).read_text()

    assert "log_connections = 0" in template
    assert "log_disconnections = 0" in template
    assert "log_pooler_errors = 1" in template
    assert "stats_period = 60" in template


def test_pgbouncer_entrypoint_keeps_docker_dns_readable_after_privilege_drop():
    entrypoint = (
        Path(__file__).resolve().parents[1]
        / "compose"
        / "production"
        / "pgbouncer"
        / "entrypoint"
    ).read_text()

    assert 'chmod a+r /etc/resolv.conf' in entrypoint
    assert 'exec pgbouncer "$runtime_dir/pgbouncer.ini"' in entrypoint


def _compose_path(compose_file: str) -> Path:
    return Path(__file__).resolve().parents[1] / compose_file


def _service_environment(compose_path: Path, service_name: str) -> dict[str, str]:
    service_block = _service_block(compose_path, service_name)
    env_start = _find_line(service_block, "    environment:")

    env: dict[str, str] = {}
    for line in service_block[env_start + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _indent(line) <= 4:
            break
        key, separator, value = line.strip().partition(":")
        if separator:
            env[key] = value.strip().strip('"')
    return env


def _service_block(compose_path: Path, service_name: str) -> list[str]:
    lines = compose_path.read_text().splitlines()
    service_start = _find_line(lines, f"  {service_name}:")
    service_end = _find_next_service_line(lines, service_start + 1)
    return lines[service_start:service_end]


def _find_line(lines: list[str], needle: str) -> int:
    for index, line in enumerate(lines):
        if line == needle:
            return index
    raise AssertionError(f"Could not find line: {needle}")


def _find_next_service_line(lines: list[str], start: int) -> int:
    for index, line in enumerate(lines[start:], start=start):
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            return index
    return len(lines)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))
