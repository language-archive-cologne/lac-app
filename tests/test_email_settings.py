from config.settings.email import parse_admins


def test_parse_admins_returns_empty_list_for_blank_env_value():
    assert parse_admins("") == []


def test_parse_admins_supports_named_admin_addresses():
    assert parse_admins("Operations <ops@example.test>") == [
        ("Operations", "ops@example.test"),
    ]


def test_parse_admins_supports_multiple_addresses_and_plain_addresses():
    assert parse_admins(
        "Operations <ops@example.test>, alerts@example.test",
    ) == [
        ("Operations", "ops@example.test"),
        ("alerts@example.test", "alerts@example.test"),
    ]
