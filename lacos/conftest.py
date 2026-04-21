import pytest

from lacos.users.models import User
from lacos.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture
def enroll_mfa(db):
    def _enroll(user: User):
        from allauth.mfa.models import Authenticator

        authenticator, _ = Authenticator.objects.get_or_create(
            user=user,
            type=Authenticator.Type.TOTP,
            defaults={"data": {"secret": "test-secret"}},
        )
        return authenticator

    return _enroll
