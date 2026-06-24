from pathlib import Path

CLARIN_PROXY_IDP_METADATA_URL = (
    "https://infra.clarin.eu/aai/prod_md_about_clarin_erics_proxy-idp.xml"
)
DFN_EDUGAIN_METADATA_URL = (
    "https://www.aai.dfn.de/fileadmin/metadata/dfn-aai-edugain+idp-metadata.xml"
)


def _production_compose_path() -> Path:
    return Path(__file__).resolve().parents[1] / "docker-compose.production.yml"


def _service_environment(service_name: str) -> dict[str, str]:
    lines = _production_compose_path().read_text().splitlines()
    service_start = _find_line(lines, f"  {service_name}:")
    service_end = _find_next_service_line(lines, service_start + 1)
    env_start = _find_line(lines, "    environment:", service_start, service_end)

    env: dict[str, str] = {}
    for line in lines[env_start + 1 : service_end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _indent(line) <= 4:
            break
        key, separator, value = line.strip().partition(":")
        if separator:
            env[key] = value.strip().strip('"')
    return env


def _find_line(
    lines: list[str],
    needle: str,
    start: int = 0,
    end: int | None = None,
) -> int:
    for index, line in enumerate(lines[start:end], start=start):
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


def test_production_django_uses_clarin_proxy_idp_without_local_idp_fallback():
    env = _service_environment("django")

    assert env["SAML_IDP_METADATA_REMOTE"] == CLARIN_PROXY_IDP_METADATA_URL
    assert env["SAML_DIRECT_IDP_SELECTION_ENABLED"] == "false"
    assert env["SAML_METADATA_MDQ_URL"] == ""
    assert env["EDUGAIN_METADATA_URL"] == DFN_EDUGAIN_METADATA_URL
    assert env["SAML2_DISCO_URL"] == ""


def test_production_huey_uses_same_saml_sources_as_django():
    django_env = _service_environment("django")
    huey_env = _service_environment("huey")

    for key in (
        "SAML_IDP_METADATA_REMOTE",
        "SAML_DIRECT_IDP_SELECTION_ENABLED",
        "SAML_METADATA_MDQ_URL",
        "EDUGAIN_METADATA_URL",
        "SAML2_DISCO_URL",
    ):
        assert huey_env[key] == django_env[key]


def test_production_saml_config_does_not_depend_on_stale_local_metadata_file():
    for service_name in ("django", "huey"):
        env = _service_environment(service_name)

        assert env["SAML_IDP_METADATA_LOCAL"] == ""
        assert env["SAML_METADATA_REFRESH_ENABLED"] == "false"
