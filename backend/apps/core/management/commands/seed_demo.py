"""Local demo data that exercises every screen.

    python manage.py seed_demo            # create, and run the queued agent runs inline
    python manage.py seed_demo --no-agents

Two tenants with one person per role. Acme gets an approved requisition with
an approved JD, candidates whose resumes went through the real pipeline, a
matching run waiting for the recruiter's shortlist review, a candidate with a
scheduled interview, a requisition waiting for HR approval and a draft for the
JD studio. Globex gets a little data so tenant isolation is visible.

Everything is created through the services inside a tenant scope, the same
path an API request takes. Runs as the runtime role, like the app.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.accounts.roles import Role
from apps.accounts.services import build_execution_context
from apps.core.context import ExecutionContext
from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope

DEMO_PASSWORD = "demo-pass-2026"  # noqa: S105 - local demo data only; refused unless DEBUG

PEOPLE = {
    "hr_admin": ("Hema", "Rao", [Role.HR_ADMIN]),
    "hr_lead": ("Ishaan", "Bose", [Role.HR_ADMIN]),
    "recruiter": ("Riya", "Sen", [Role.RECRUITER]),
    "manager": ("Manoj", "Pillai", [Role.HIRING_MANAGER]),
    "interviewer": ("Ira", "Joshi", [Role.INTERVIEWER]),
    "finance": ("Farhan", "Ali", [Role.FINANCE_APPROVER]),
    "auditor": ("Anita", "Kapoor", [Role.AUDITOR]),
}
TENANTS = {"acme": "Acme Corp", "globex": "Globex"}

RESUMES = {
    "Priya Raman": [
        "Priya Raman",
        "priya.raman@example.com | +91 98400 11223 | linkedin.com/in/priyaraman",
        "Summary",
        "Backend engineer who builds reliable APIs and AI pipelines.",
        "Experience",
        "Senior Engineer, Acme Labs 2021-2024",
        "Built FastAPI services in Python and ran them on AWS.",
        "Designed LangGraph agents that review contracts with a RAG search layer.",
        "Engineer, Beta Systems 2018-2021",
        "Maintained Django apps and PostgreSQL databases.",
        "Education",
        "B.Tech, Anna University 2018",
        "Skills",
        "Python, FastAPI, Django, PostgreSQL, AWS, LangGraph, Docker",
    ],
    "Arjun Mehta": [
        "Arjun Mehta",
        "arjun.mehta@example.com | +91 99000 22334",
        "Experience",
        "Software Engineer, Gamma Tech 2019-2024",
        "Built Flask and FastAPI microservices in Python.",
        "Ran Kafka pipelines on Kubernetes.",
        "Education",
        "B.E., PSG College of Technology 2019",
        "Skills",
        "Python, FastAPI, Flask, Kafka, Kubernetes, Redis",
    ],
    "Sara Thomas": [
        "Sara Thomas",
        "sara.thomas@example.com",
        "Experience",
        "ML Engineer, Delta AI 2020-2024",
        "Built a RAG assistant with LangChain and Qdrant on AWS.",
        "Wrote LangGraph workflows with human review steps.",
        "Education",
        "M.Tech, IIT Madras 2020",
        "Skills",
        "Python, LangChain, LangGraph, Qdrant, PyTorch, AWS",
        "Certifications",
        "AWS Certified Machine Learning Specialty, 2023",
    ],
    "Nisha Verma": [
        "Nisha Verma",
        "nisha.verma@example.com",
        "Experience",
        "Platform Engineer, Zeta Cloud 2019-2024",
        "Built FastAPI gateways in Python on AWS and Kubernetes.",
        "Skills",
        "Python, FastAPI, AWS, Kubernetes, Terraform",
    ],
    "Karthik Iyer": [
        "Karthik Iyer",
        "karthik.iyer@example.com",
        "Experience",
        "Java Developer, Epsilon 2017-2024",
        "Built Spring Boot services and Angular front ends.",
        "Education",
        "B.Sc Computer Science, Madras University 2017",
        "Skills",
        "Java, Spring, Angular, MySQL",
    ],
}


class Command(BaseCommand):
    help = "Create demo tenants, users, requisitions, candidates and agent runs for local development."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--no-agents", action="store_true", help="Leave agent runs queued for the worker.")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG on.")
        for slug, name in TENANTS.items():
            tenant, _ = Tenant.objects.get_or_create(slug=slug, defaults={"name": name})
            users = self._people(tenant)
            with tenant_scope(tenant.id):
                from apps.requisitions.models import JobRequisition

                already = JobRequisition.objects.exists()
            if already:
                self.stdout.write(f"{name}: already seeded")
                continue
            if slug == "acme":
                self._acme(tenant, users, run_agents=not options["no_agents"])
            else:
                self._globex(tenant, users)
            self.stdout.write(f"{name}: seeded ({', '.join(u.username for u in users.values())})")
        self.stdout.write(self.style.SUCCESS(f"Done. Every demo user's password is {DEMO_PASSWORD!r}."))

    # ------------------------------------------------------------------ helpers

    def _people(self, tenant: Tenant) -> dict[str, User]:
        users = {}
        for key, (first, last, roles) in PEOPLE.items():
            username = f"{tenant.slug}_{key}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.test", "first_name": first, "last_name": last},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            Membership.objects.get_or_create(tenant=tenant, user=user, defaults={"roles": roles})
            users[key] = user
        return users

    @staticmethod
    def _ctx(user: User, tenant: Tenant) -> ExecutionContext:
        return build_execution_context(user_id=user.pk, requested_tenant_id=tenant.id)

    def _setup_tenant(self, tenant: Tenant, users: dict[str, User]) -> Any:
        from apps.communications.services import create_template
        from apps.governance.models import RetentionPolicy
        from apps.jobs.services import create_template as create_jd_template
        from apps.requisitions.services import create_comp_band

        admin = self._ctx(users["hr_admin"], tenant)
        with tenant_scope(tenant.id):
            band = create_comp_band(
                admin,
                department="Engineering",
                level="L4",
                min_salary=Decimal("2400000"),
                max_salary=Decimal("3600000"),
            )
            create_comp_band(
                admin,
                department="Engineering",
                level="L5",
                min_salary=Decimal("3400000"),
                max_salary=Decimal("5000000"),
            )
            create_jd_template(
                admin,
                name="Engineering JD",
                department="Engineering",
                body=(
                    "# {title}\n## About the role\n## What you will do\n## What you need\n"
                    "## Nice to have\n## How we hire\n"
                    "House style: plain English, address the reader as 'you', no jargon."
                ),
            )
            create_template(
                admin,
                key="decline-default",
                name="Kind decline",
                kind="decline",
                subject="Your application for {{ job_title }}",
                body="Hi {{ candidate_first_name }},\n\nThank you for applying for {{ job_title }} at "
                "{{ company_name }}. We have decided not to move forward this time. We are grateful "
                "for your time and wish you the best.\n\nKind regards,\n{{ recruiter_name }}",
            )
            RetentionPolicy.objects.get_or_create(target="candidates", defaults={"retain_days": 365})
            RetentionPolicy.objects.get_or_create(target="agent_runs", defaults={"retain_days": 180})
        return band

    def _approved_requisition(self, tenant: Tenant, users: dict[str, User], band: Any, **fields: Any) -> Any:
        from apps.approvals.models import ApprovalRequest
        from apps.approvals.services import decide
        from apps.jobs.services import approve_jd, create_jd_draft
        from apps.requisitions.services import create_requisition, submit_requisition

        recruiter = self._ctx(users["recruiter"], tenant)
        with tenant_scope(tenant.id):
            requisition = create_requisition(
                recruiter, hiring_manager_id=users["manager"].pk, comp_band_id=band.id, **fields
            )
            submit_requisition(recruiter, requisition_id=requisition.id)
            approval = ApprovalRequest.objects.get(target_id=requisition.id, kind="requisition")
            decide(self._ctx(users["hr_admin"], tenant), request_id=approval.id, decision="approve")
            requirements = [{"name": s, "level": "mandatory"} for s in fields["must_have_skills"]]
            requirements += [{"name": s, "level": "preferred"} for s in fields.get("nice_to_have_skills", [])]
            jd = create_jd_draft(
                recruiter,
                requisition_id=requisition.id,
                title=fields["title"],
                summary=fields["summary"],
                requirements=requirements,
                responsibilities=["Design, build and run production services."],
                body=f"# {fields['title']}\n\n{fields['summary']}",
            )
            approve_jd(recruiter, jd)
        return requisition

    def _candidate(
        self, tenant: Tenant, users: dict[str, User], requisition: Any, name: str, talent_pool: bool = False
    ) -> Any:
        from apps.applications.services import create_application
        from apps.candidates.services import create_candidate
        from apps.documents.services import complete_upload, receive_upload, request_upload
        from apps.documents.tasks import process_document
        from document_ai.pdf import make_pdf

        recruiter = self._ctx(users["recruiter"], tenant)
        email = f"{name.lower().replace(' ', '.')}@example.com"
        with tenant_scope(tenant.id):
            candidate = create_candidate(
                recruiter,
                full_name=name,
                email=email,
                talent_pool_consent=talent_pool,
                consent_source="careers site application form",
            )
            application = (
                create_application(recruiter, requisition_id=requisition.id, candidate_id=candidate.id)
                if requisition
                else None
            )
            document, link = request_upload(
                recruiter, candidate_id=candidate.id, filename=f"{name.split()[0].lower()}-resume.pdf"
            )
            receive_upload(recruiter, token=link.url.rstrip("/").split("/")[-1], data=make_pdf(RESUMES[name]))
        # complete_upload queues the pipeline on commit; in the seed we run it right here instead.
        with tenant_scope(tenant.id):
            complete_upload(recruiter, document_id=document.id)
        process_document(document_id=str(document.id), tenant_id=str(tenant.id))
        return candidate, application

    def _run_queued(self, tenant: Tenant) -> None:
        from agent_engine.runtime import execute_queued

        results = execute_queued(tenant.id)
        if results:
            self.stdout.write(f"  agent runs: {', '.join(results)}")

    # ------------------------------------------------------------------ tenants

    def _acme(self, tenant: Tenant, users: dict[str, User], *, run_agents: bool) -> None:
        from agent_engine.runtime import start_run
        from apps.applications.services import record_decision
        from apps.integrations.models import CalendarBusyBlock
        from apps.interviews.scheduling import Interval
        from apps.interviews.services import confirm_slot, create_interview, propose_slots
        from apps.requisitions.services import create_requisition, submit_requisition

        band = self._setup_tenant(tenant, users)
        backend = self._approved_requisition(
            tenant,
            users,
            band,
            title="Senior Python Engineer",
            department="Engineering",
            location="Chennai",
            level="L4",
            summary="Build the APIs and agent pipelines behind our HR products, with a focus on "
            "reliability and clear evidence for every recommendation.",
            must_have_skills=["Python", "FastAPI", "LangGraph", "RAG"],
            nice_to_have_skills=["AWS", "Kubernetes"],
        )
        apps = {}
        for name in ("Priya Raman", "Arjun Mehta", "Sara Thomas", "Karthik Iyer"):
            _, apps[name] = self._candidate(tenant, users, backend, name)
        self._candidate(tenant, users, None, "Nisha Verma", talent_pool=True)  # talent pool only, no application

        recruiter = self._ctx(users["recruiter"], tenant)
        with tenant_scope(tenant.id):
            create_requisition(
                recruiter,
                title="GenAI Engineer",
                department="Engineering",
                level="L5",
                hiring_manager_id=users["manager"].pk,
                must_have_skills=["Python", "LLM"],
                summary="Prototype and ship LLM features.",
            )
            submitted = create_requisition(
                recruiter,
                title="Data Engineer",
                department="Engineering",
                level="L4",
                location="Bengaluru",
                hiring_manager_id=users["manager"].pk,
                comp_band_id=band.id,
                must_have_skills=["SQL", "Airflow"],
                summary="Own the pipelines that feed recruiting analytics and dashboards.",
            )
            submit_requisition(recruiter, requisition_id=submitted.id)

            # Sara is further along: shortlisted, with a scheduled interview.
            sara = apps["Sara Thomas"]
            record_decision(
                recruiter,
                application_id=sara.id,
                decision="advance",
                to_stage="shortlisted",
                reason="RAG and LangGraph work is directly relevant.",
            )
            interview = create_interview(
                recruiter,
                application_id=sara.id,
                title="Technical interview",
                panel_user_ids=[users["interviewer"].pk, users["manager"].pk],
            )
            start = (timezone.now() + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)
            slot = propose_slots(
                recruiter, interview_id=interview.id, run_id=None, slots=[Interval(start, start + timedelta(hours=1))]
            )[0]
            confirm_slot(recruiter, interview_id=interview.id, slot_id=slot.id)
            busy = timezone.now().replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
            CalendarBusyBlock.objects.create(
                user=users["interviewer"], start=busy, end=busy + timedelta(hours=2), title="Team planning"
            )

        if run_agents:
            self._run_queued(tenant)  # resume parsing for every upload
            with tenant_scope(tenant.id):
                start_run(recruiter, kind="matching", params={"requisition_id": backend.id})
            self._run_queued(tenant)  # the matching run pauses for the recruiter's shortlist review

    def _globex(self, tenant: Tenant, users: dict[str, User]) -> None:
        band = self._setup_tenant(tenant, users)
        self._approved_requisition(
            tenant,
            users,
            band,
            title="Platform Engineer",
            department="Engineering",
            location="Pune",
            level="L4",
            summary="Run the platform our products are built on, with strong ownership of reliability.",
            must_have_skills=["Go", "Kubernetes"],
        )
