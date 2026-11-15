from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope


@shared_task
def fail_stuck_runs() -> int:
    """Beat job: a run stuck in running or queued (a worker died mid-run) is marked failed so people see it."""
    from apps.agents.models import AgentRun
    from apps.core.realtime import publish_run_event

    cutoff = timezone.now() - timedelta(minutes=settings.AGENT_RUN_STUCK_MINUTES)
    count = 0
    for tenant_id in Tenant.objects.filter(is_active=True).values_list("id", flat=True):
        with tenant_scope(tenant_id):
            stuck = AgentRun.objects.filter(
                status__in=[AgentRun.Status.RUNNING, AgentRun.Status.QUEUED], updated_at__lt=cutoff
            )
            for run in stuck:
                run.status = AgentRun.Status.FAILED
                run.error = f"No progress for {settings.AGENT_RUN_STUCK_MINUTES} minutes; marked failed."
                run.finished_at = timezone.now()
                run.save()
                publish_run_event(run.id, {"type": "run.finished", "status": run.status, "error": run.error})
                count += 1
    return count


@shared_task
def run_nightly_evals() -> dict[str, bool]:
    """Beat job: run the offline eval suites and store EvalResult rows."""
    from evals.runner import run_all

    return {result.suite: result.passed for result in run_all()}
