"""
Shared fixtures.

Every test that uses the database runs as the runtime role (hr_app), not the
owner role that created the test database. Without this, the tests would
bypass Row-Level Security and could pass while production leaks data.
"""

from collections.abc import Callable, Iterator

import pytest
from django.conf import settings
from django.db import DatabaseError, connection
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.core.models import Tenant
from apps.core.tests.factories import TenantFactory


@pytest.fixture(autouse=True)
def _run_as_app_role(request: pytest.FixtureRequest) -> Iterator[None]:
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        yield
        return
    transactional = marker.kwargs.get("transaction", bool(marker.args and marker.args[0]))
    request.getfixturevalue("transactional_db" if transactional else "db")

    role = connection.ops.quote_name(settings.DATABASE_APP_ROLE)
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {role}")
    yield
    try:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")  # before a transactional test's TRUNCATE flush
    except DatabaseError:
        pass  # transaction already aborted; the test rollback resets the role


@pytest.fixture
def tenant_a() -> Tenant:
    return TenantFactory(name="Acme Corp", slug="acme")


@pytest.fixture
def tenant_b() -> Tenant:
    return TenantFactory(name="Globex", slug="globex")


MakeMember = Callable[..., User]


@pytest.fixture
def make_member() -> MakeMember:
    """make_member(tenant, "recruiter", ...) -> a user with those roles in that tenant."""

    def make(tenant: Tenant, *roles: str, user: User | None = None) -> User:
        user = user or UserFactory()
        MembershipFactory(tenant=tenant, user=user, roles=list(roles))
        return user

    return make


ClientFor = Callable[..., APIClient]


@pytest.fixture
def client_for() -> ClientFor:
    """client_for(user, tenant=None) -> an authenticated APIClient, optionally pinned to a tenant."""

    def make(user: User, tenant: Tenant | None = None) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        if tenant is not None:
            client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
        return client

    return make


@pytest.fixture(autouse=True)
def _reset_scripted_model() -> Iterator[None]:
    """Scripted LLM responses never leak from one test into the next."""
    from agent_engine.llm import fake

    fake.reset()
    yield
    fake.reset()
