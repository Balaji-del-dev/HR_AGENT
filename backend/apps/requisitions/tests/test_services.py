"""Services enforce tenant and policy rules for any caller: API views today, agent tools later."""

import uuid

import pytest

from apps.accounts.roles import Role
from apps.core.context import ExecutionContext
from apps.core.exceptions import NotFound, PolicyDenied, TenantScopeError
from apps.core.tenancy import tenant_scope
from apps.requisitions import services
from apps.requisitions.tests.factories import JobRequisitionFactory

pytestmark = pytest.mark.django_db


def ctx_for(user, tenant, *roles: str) -> ExecutionContext:
    return ExecutionContext(user_id=user.pk, tenant_id=tenant.id, roles=frozenset(roles))


def test_service_refuses_to_run_without_its_tenant_active(tenant_a, make_member) -> None:
    admin = make_member(tenant_a, Role.HR_ADMIN)
    manager = make_member(tenant_a, Role.HIRING_MANAGER)
    with pytest.raises(TenantScopeError):
        services.create_requisition(
            ctx_for(admin, tenant_a, Role.HR_ADMIN), title="t", department="d", hiring_manager_id=manager.pk
        )


def test_service_refuses_a_context_for_another_tenant(tenant_a, tenant_b, make_member) -> None:
    admin = make_member(tenant_a, Role.HR_ADMIN)
    requisition = JobRequisitionFactory(tenant=tenant_a)
    with tenant_scope(tenant_b.id), pytest.raises(TenantScopeError):
        services.submit_requisition(ctx_for(admin, tenant_a, Role.HR_ADMIN), requisition_id=requisition.pk)


def test_forged_roles_still_cannot_reach_another_tenants_rows(tenant_a, tenant_b, make_member) -> None:
    """Even an hr_admin context for tenant B, with B active, cannot find A's requisition."""
    requisition = JobRequisitionFactory(tenant=tenant_a)
    intruder = make_member(tenant_b, Role.HR_ADMIN)
    with tenant_scope(tenant_b.id), pytest.raises(NotFound):
        services.submit_requisition(ctx_for(intruder, tenant_b, Role.HR_ADMIN), requisition_id=requisition.pk)


def test_policy_denial_is_independent_of_the_view(tenant_a, make_member) -> None:
    interviewer = make_member(tenant_a, Role.INTERVIEWER)
    with tenant_scope(tenant_a.id), pytest.raises(PolicyDenied):
        services.create_requisition(
            ctx_for(interviewer, tenant_a, Role.INTERVIEWER), title="t", department="d", hiring_manager_id=uuid.uuid4()
        )
