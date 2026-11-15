import uuid

import pytest
import redis
from celery import shared_task

from apps.core.context import ExecutionContext
from apps.core.exceptions import TenantScopeError
from apps.core.tasks import TenantTask, enqueue_on_commit
from apps.core.tenancy import get_current_tenant_id
from apps.requisitions.models import JobRequisition
from apps.requisitions.tests.factories import JobRequisitionFactory


@shared_task(base=TenantTask, name="tests.count_requisitions")
def count_requisitions(*, tenant_id: str) -> dict[str, object]:
    return {"tenant": get_current_tenant_id(), "count": JobRequisition.objects.count()}


SEEN: list[tuple[object, int]] = []


@shared_task(base=TenantTask, name="tests.record_tenant")
def record_tenant(*, tenant_id: str) -> None:
    SEEN.append((get_current_tenant_id(), JobRequisition.objects.count()))


# --- Celery TenantTask --------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_task_runs_inside_its_tenant(tenant_a, tenant_b) -> None:
    JobRequisitionFactory(tenant=tenant_a)
    JobRequisitionFactory(tenant=tenant_a)
    JobRequisitionFactory(tenant=tenant_b)

    result = count_requisitions.apply(kwargs={"tenant_id": str(tenant_a.id)}).get()

    assert result == {"tenant": tenant_a.id, "count": 2}
    assert get_current_tenant_id() is None


@pytest.mark.django_db
def test_tenant_task_without_tenant_is_refused() -> None:
    with pytest.raises(TenantScopeError, match="without tenant_id"):
        count_requisitions.apply().get()


@pytest.mark.django_db
def test_enqueue_on_commit_runs_after_commit_for_the_context_tenant(
    tenant_a, django_capture_on_commit_callbacks
) -> None:
    JobRequisitionFactory(tenant=tenant_a)
    ctx = ExecutionContext(user_id=uuid.uuid4(), tenant_id=tenant_a.id, roles=frozenset())
    SEEN.clear()

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        enqueue_on_commit(record_tenant, ctx)
        assert SEEN == []  # nothing runs before commit

    assert len(callbacks) == 1
    assert SEEN == [(tenant_a.id, 1)]


# --- Request id middleware and health endpoints ----------------------------------------


@pytest.mark.django_db
def test_request_id_is_generated_and_returned(client) -> None:
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_safe_incoming_request_id_is_kept(client) -> None:
    response = client.get("/healthz/", HTTP_X_REQUEST_ID="gateway-req-12345")
    assert response["X-Request-ID"] == "gateway-req-12345"


@pytest.mark.django_db
def test_unsafe_incoming_request_id_is_replaced(client) -> None:
    response = client.get("/healthz/", HTTP_X_REQUEST_ID="has spaces <script>")
    assert response["X-Request-ID"] != "has spaces <script>"
    assert len(response["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_readiness_reports_redis_outage(client, monkeypatch) -> None:
    class DownRedis:
        def ping(self) -> None:
            raise redis.ConnectionError("down")

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: DownRedis()))
    response = client.get("/readyz/")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "ok", "redis": "unavailable"}


@pytest.mark.django_db
def test_readiness_ok(client, monkeypatch) -> None:
    class UpRedis:
        def ping(self) -> bool:
            return True

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: UpRedis()))
    assert client.get("/readyz/").json() == {"status": "ok"}
