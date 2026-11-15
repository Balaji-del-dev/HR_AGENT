"""Candidate profiles with real resumes, read by the real pipeline.

    python manage.py seed_candidates                 # 100 candidates for Acme Corp, parsed by the worker
    python manage.py seed_candidates --count 40 --tenant globex
    python manage.py seed_candidates --wait          # also wait until every resume is parsed
    python manage.py seed_candidates --inline        # parse here instead of in the Celery worker
    python manage.py seed_candidates --spread        # spread "added by" across every recruiter

Each candidate gets consent, a source and a generated PDF resume. The resume goes through
upload, validation, extraction, masking and the resume-parsing agent, exactly like an upload
from the app, so every skill, job and degree on the profile links to the resume line it
came from. No jobs or applications are created. Generated people are fictional; the
generator is seeded, so the same command gives the same 100 people. Safe to run again:
candidates already created by this command are skipped. Local development only.
"""

import random
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import Membership
from apps.accounts.services import build_execution_context
from apps.core.models import Tenant
from apps.core.tenancy import tenant_scope

FIRST = """Aarav Aditi Akash Ambika Amit Anjali Ankit Aparna Arjun Asha Bharat Chitra Daksh Deepak Devika
Dhruv Esha Gaurav
Geeta Harish Harini Imran Isha Jai Janani Karan Keerthi Krishna Lavanya Madhav Mahima Manish Maya Mukesh Nandini Naveen
Nikita Omkar Pallavi Pranav Preeti Rajat Ramya Ravi Rekha Sahil Sanjana Santosh Shreya Shyam Sindhu Sumit Swati Tejas
Uma Varun Vidya Vinay Yamini Yash Zaid""".split()
LAST = """Agarwal Bhatt Chakraborty Chandran Chopra Dutta Fernandes Ganesan Ghosh Hegde Jayaraman Kamath
Khanna Kumar Lal
Mathew Mishra Mukherjee Murthy Naidu Natarajan Pandey Parekh Prasad Rajan Ramachandran Rangan Saini Sastry Sethi Singh
Srinivasan Subramanian Thakur Tiwari Varghese Venkatesh Wadhwa Yadav Zacharia""".split()
CITIES = [
    "Chennai",
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Delhi NCR",
    "Kochi",
    "Coimbatore",
    "Ahmedabad",
    "Kolkata",
    "Jaipur",
    "Remote",
]
COMPANIES = [
    "Northwind Systems",
    "Bluepeak Labs",
    "Cedar Technologies",
    "Orbit Analytics",
    "Zenith Software",
    "Lotus Digital",
    "Kestrel Labs",
    "Indigo Fintech",
    "Riverstone Solutions",
    "Saffron Health Tech",
    "Monsoon Labs",
    "Banyan Data",
    "Peacock Payments",
    "Tidewater Logistics",
    "Quartz Networks",
    "Coral Mobility",
    "Granite Insurance Tech",
    "Harbor Commerce",
    "Nilgiri Systems",
    "Marigold Retail",
    "Sundial Media",
    "Everest Energy Tech",
]
SCHOOLS = [
    "Anna University",
    "IIT Madras",
    "NIT Trichy",
    "VIT Vellore",
    "PSG College of Technology",
    "BITS Pilani",
    "Jadavpur University",
    "Savitribai Phule Pune University",
    "Osmania University",
    "Amrita Vishwa Vidyapeetham",
    "Manipal Institute of Technology",
    "IIIT Hyderabad",
    "University of Delhi",
    "University of Mumbai",
    "SRM Institute of Science and Technology",
    "College of Engineering Guindy",
    "NIT Surathkal",
    "IIM Kozhikode",
]
SOURCES = [("applied", 40), ("referral", 15), ("sourced", 20), ("talent_pool", 20), ("ats_import", 5)]


@dataclass(frozen=True)
class Track:
    titles: tuple[str, ...]  # junior to senior
    skills: tuple[str, ...]  # names from document_ai.vocabulary, so extraction can cite them
    work: tuple[str, ...]  # bullet lines; {a} and {b} become skills
    degrees: tuple[str, ...]
    certs: tuple[str, ...] = ()
    summary: str = ""


TRACKS = [
    Track(
        ("Software Engineer", "Senior Software Engineer", "Lead Backend Engineer"),
        (
            "Python",
            "Django",
            "FastAPI",
            "Flask",
            "PostgreSQL",
            "Redis",
            "Celery",
            "Docker",
            "AWS",
            "Kubernetes",
            "Kafka",
        ),
        (
            "Built {a} services backed by {b} for a high-traffic product.",
            "Cut API latency by 40% using {a} and {b} caching.",
            "Owned the {a} pipeline and its on-call rota.",
            "Moved batch jobs from cron to {a} with {b}.",
        ),
        ("B.Tech Computer Science", "B.E. Computer Science", "M.Tech Software Engineering"),
        ("AWS Certified Developer Associate", "Certified Kubernetes Application Developer"),
        "Backend engineer who ships reliable APIs and cares about clear, tested code.",
    ),
    Track(
        ("Java Developer", "Senior Java Engineer", "Technical Lead"),
        ("Java", "Spring", "SpringBoot", "Hibernate", "MySQL", "Kafka", "Docker", "Jenkins", "AWS", "Redis"),
        (
            "Designed {a} microservices with {b} for payments.",
            "Migrated a monolith to {a} and {b}.",
            "Set up {a} pipelines for twelve services.",
            "Tuned {a} queries and {b} for month-end loads.",
        ),
        ("B.E. Information Technology", "B.Tech Computer Science", "M.Sc Computer Science"),
        ("Oracle Certified Professional Java SE", "AWS Certified Solutions Architect Associate"),
        "Java engineer focused on payments and dependable microservices.",
    ),
    Track(
        ("Frontend Developer", "Senior Frontend Engineer", "Frontend Lead"),
        (
            "JavaScript",
            "TypeScript",
            "React",
            "Next.js",
            "Redux",
            "HTML",
            "CSS",
            "Tailwind",
            "Jest",
            "Cypress",
            "Figma",
        ),
        (
            "Built a design system in {a} and {b} used by six teams.",
            "Rewrote the checkout in {a} with {b}.",
            "Raised accessibility scores using {a} and {b} tests.",
            "Worked with designers in {a} to ship {b} screens.",
        ),
        ("B.Tech Computer Science", "B.Sc Computer Science", "Bachelor of Computer Applications"),
        ("Meta Front-End Developer Certificate",),
        "Frontend engineer who turns designs into fast, accessible interfaces.",
    ),
    Track(
        ("Full Stack Developer", "Senior Full Stack Engineer", "Engineering Lead"),
        ("Node.js", "Express", "React", "TypeScript", "MongoDB", "PostgreSQL", "GraphQL", "AWS", "Docker"),
        (
            "Built {a} and {b} features end to end for a SaaS product.",
            "Introduced {a} for the {b} API layer.",
            "Ran {a} on {b} with zero-downtime deploys.",
            "Mentored three engineers on {a} and {b}.",
        ),
        ("B.Tech Information Technology", "B.E. Computer Science", "M.Tech Computer Science"),
        ("AWS Certified Cloud Practitioner",),
        "Full stack engineer comfortable from the database to the browser.",
    ),
    Track(
        ("Data Engineer", "Senior Data Engineer", "Data Platform Lead"),
        ("SQL", "Python", "Spark", "PySpark", "Airflow", "dbt", "Snowflake", "BigQuery", "Kafka", "Databricks"),
        (
            "Built {a} pipelines that load {b} every hour.",
            "Modelled the warehouse in {a} on {b}.",
            "Moved streaming ingest to {a} and {b}.",
            "Cut {a} costs by a third by tuning {b} jobs.",
        ),
        ("B.Tech Computer Science", "M.Sc Statistics", "M.Tech Data Science"),
        ("Google Professional Data Engineer", "Databricks Certified Data Engineer Associate"),
        "Data engineer who builds trustworthy pipelines and warehouses.",
    ),
    Track(
        ("ML Engineer", "Senior ML Engineer", "Applied AI Lead"),
        (
            "Python",
            "PyTorch",
            "TensorFlow",
            "scikit-learn",
            "LangChain",
            "LangGraph",
            "RAG",
            "LLM",
            "HuggingFace",
            "MLflow",
            "SageMaker",
            "Qdrant",
        ),
        (
            "Built a {a} assistant with {b} retrieval over policy documents.",
            "Trained {a} models and tracked them in {b}.",
            "Deployed {a} services on {b} with human review steps.",
            "Evaluated {a} answers with {b} test sets.",
        ),
        ("M.Tech Computer Science", "M.S. Machine Learning", "B.Tech Electronics"),
        ("AWS Certified Machine Learning Specialty", "TensorFlow Developer Certificate"),
        "ML engineer building retrieval and agent systems with human oversight.",
    ),
    Track(
        ("DevOps Engineer", "Site Reliability Engineer", "Platform Engineering Lead"),
        (
            "Linux",
            "Docker",
            "Kubernetes",
            "Terraform",
            "Ansible",
            "AWS",
            "GCP",
            "Prometheus",
            "Grafana",
            "Jenkins",
            "ArgoCD",
            "Helm",
        ),
        (
            "Ran {a} clusters for forty services with {b}.",
            "Wrote {a} modules for every environment, reviewed in {b}.",
            "Set up {a} alerts and {b} dashboards for on-call.",
            "Moved deploys to {a} with {b} rollbacks.",
        ),
        ("B.E. Electronics", "B.Tech Computer Science", "Diploma in Computer Engineering"),
        ("Certified Kubernetes Administrator", "HashiCorp Certified Terraform Associate"),
        "Platform engineer who keeps systems observable and deploys boring.",
    ),
    Track(
        ("QA Engineer", "Senior QA Automation Engineer", "QA Lead"),
        ("Selenium", "Playwright", "Cypress", "Pytest", "JUnit", "Postman", "Jira", "Java", "Python"),
        (
            "Automated regression suites in {a} and {b}.",
            "Cut release testing from three days to one with {a}.",
            "Built API checks in {a} run on every merge with {b}.",
            "Tracked defects and coverage in {a}.",
        ),
        ("B.E. Computer Science", "B.Sc Information Technology", "Bachelor of Computer Applications"),
        ("ISTQB Certified Tester Foundation Level",),
        "QA engineer who turns manual checks into fast, reliable automation.",
    ),
    Track(
        ("Android Developer", "Senior Mobile Engineer", "Mobile Lead"),
        ("Kotlin", "Swift", "Java", "REST", "GraphQL", "Postman", "Jira"),
        (
            "Shipped {a} apps with offline sync over {b}.",
            "Rebuilt the payments flow in {a} using {b}.",
            "Reduced crash rate below 0.2% in the {a} app.",
            "Worked with designers on {a} screens backed by {b}.",
        ),
        ("B.Tech Computer Science", "B.E. Electronics and Communication"),
        ("Associate Android Developer",),
        "Mobile engineer who builds smooth, dependable apps.",
    ),
    Track(
        ("Data Analyst", "Senior Data Analyst", "Analytics Manager"),
        ("SQL", "Excel", "Tableau", "PowerBI", "Looker", "Python", "Pandas"),
        (
            "Built {a} dashboards on {b} for the sales leadership team.",
            "Automated weekly {a} reports with {b}.",
            "Analysed churn in {a} and presented findings in {b}.",
            "Defined metrics with finance in {a}.",
        ),
        ("B.Sc Statistics", "Bachelor of Commerce", "MBA Business Analytics"),
        ("Microsoft Certified Power BI Data Analyst Associate", "Tableau Desktop Specialist"),
        "Analyst who turns messy data into decisions people trust.",
    ),
    Track(
        ("Product Designer", "Senior Product Designer", "Design Lead"),
        ("Figma", "HTML", "CSS", "Jira", "Confluence", "Agile"),
        (
            "Designed onboarding flows in {a} that lifted activation.",
            "Ran research and documented findings in {a}.",
            "Built the component library in {a} with engineering.",
            "Prototyped {a} screens and tested them with users.",
        ),
        ("Bachelor of Design", "Master of Design", "B.Tech Computer Science"),
        ("Google UX Design Certificate",),
        "Designer who pairs research with clear, buildable interfaces.",
    ),
    Track(
        ("HR Executive", "HR Business Partner", "Senior HR Business Partner"),
        ("Workday", "Excel", "SAP", "ServiceNow", "Jira"),
        (
            "Ran onboarding for 300 hires a year in {a}.",
            "Moved HR requests to {a} and cut response time by half.",
            "Built headcount reports in {a} for leadership.",
            "Led performance cycles across four teams using {a}.",
        ),
        ("MBA Human Resources", "Bachelor of Business Administration", "Master of Social Work"),
        ("SHRM Certified Professional",),
        "HR partner who makes people processes simple and fair.",
    ),
    Track(
        ("Talent Acquisition Specialist", "Senior Recruiter", "Talent Acquisition Lead"),
        ("Workday", "Excel", "Salesforce", "Jira"),
        (
            "Hired 60 engineers a year, tracked in {a}.",
            "Built sourcing reports in {a} for hiring managers.",
            "Cut time to offer by two weeks using {a} workflows.",
            "Ran campus hiring with {a} pipelines.",
        ),
        ("MBA Human Resources", "Bachelor of Arts", "Bachelor of Business Administration"),
        ("LinkedIn Certified Professional Recruiter",),
        "Recruiter who builds fair, fast hiring processes.",
    ),
    Track(
        ("Financial Analyst", "Senior Financial Analyst", "Finance Manager"),
        ("Excel", "SAP", "PowerBI", "Tableau", "SQL"),
        (
            "Owned monthly close reports in {a} and {b}.",
            "Built budget models in {a} for three business units.",
            "Automated variance analysis with {a}.",
            "Moved forecasting to {a} dashboards.",
        ),
        ("Bachelor of Commerce", "MBA Finance", "Master of Commerce"),
        ("Chartered Financial Analyst Level 1",),
        "Finance analyst who makes the numbers clear and on time.",
    ),
    Track(
        ("Project Coordinator", "Project Manager", "Program Manager"),
        ("Agile", "Scrum", "Kanban", "Jira", "Confluence", "Excel"),
        (
            "Ran {a} delivery for a team of twelve.",
            "Moved planning to {a} with {b} boards.",
            "Kept releases on schedule using {a} and {b}.",
            "Wrote status reports in {a} for leadership.",
        ),
        ("B.Tech Computer Science", "MBA Operations", "Bachelor of Business Administration"),
        ("Certified Scrum Master", "PMP Certification"),
        "Delivery manager who keeps teams focused and stakeholders informed.",
    ),
]


def _pick_source(rng: random.Random) -> str:
    return rng.choices([s for s, _ in SOURCES], weights=[w for _, w in SOURCES])[0]


def build_people(count: int, seed: int = 2026) -> list[dict[str, Any]]:
    """Deterministic fictional candidates with resume lines in the shape the parser reads."""
    rng = random.Random(seed)  # noqa: S311 - fictional demo data, not security
    names: set[str] = set()
    people: list[dict[str, Any]] = []
    while len(people) < count:
        first, last = rng.choice(FIRST), rng.choice(LAST)
        name = f"{first} {last}"
        if name in names:
            continue
        names.add(name)
        track = TRACKS[len(people) % len(TRACKS)] if len(people) < len(TRACKS) else rng.choice(TRACKS)
        years = rng.randint(1, 14)
        city = rng.choice(CITIES)
        email = f"{first.lower()}.{last.lower()}@example.com"
        phone = f"+91 9{rng.randint(1000, 9999)} {rng.randint(10000, 99999)}"
        jobs = min(1 + years // 4, 3)
        end_year = 2026
        lines = [name, f"{email} | {phone} | {city}", "Summary", track.summary, "Experience"]
        companies = rng.sample(COMPANIES, jobs)
        span = max(1, years // jobs)
        for i, company in enumerate(companies):
            start_year = end_year - span
            level = min(len(track.titles) - 1, max(0, (years - i * span) // 4))
            end = "Present" if i == 0 else str(end_year)
            lines.append(f"{track.titles[level]}, {company} {start_year}-{end}")
            for template in rng.sample(track.work, 2):
                a, b = rng.sample(track.skills, 2)
                lines.append(template.format(a=a, b=b))
            end_year = start_year
        graduation = end_year - rng.randint(0, 1)
        if rng.random() > 0.05:  # a few resumes leave education out, so the profile shows the gap
            lines += ["Education", f"{rng.choice(track.degrees)}, {rng.choice(SCHOOLS)} {graduation}"]
        skills = rng.sample(track.skills, min(len(track.skills), rng.randint(5, 8)))
        lines += ["Skills", ", ".join(skills)]
        if track.certs and rng.random() < 0.35:
            lines += ["Certifications", f"{rng.choice(track.certs)}, {rng.randint(max(graduation, 2015), 2025)}"]
        source = _pick_source(rng)
        people.append(
            {
                "full_name": name,
                "email": email,
                "phone": phone,
                "location": city,
                "source": source,
                "talent_pool": source == "talent_pool" or rng.random() < 0.55,
                "title": track.titles[0],
                "lines": lines,
                "external_id": f"seed-{len(people) + 1:03d}",
            }
        )
    return people


class Command(BaseCommand):
    help = (
        "Create fictional candidates with resumes that go through the real parsing pipeline (local development only)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--tenant", default="acme", help="Tenant slug (default acme).")
        parser.add_argument("--wait", action="store_true", help="Wait until the worker has parsed every resume.")
        parser.add_argument("--inline", action="store_true", help="Parse in this process instead of the Celery worker.")
        parser.add_argument(
            "--spread",
            action="store_true",
            help="Spread the candidates across every recruiter. By default the demo recruiter "
            "(<tenant>_recruiter) adds them all, so that sign-in sees all of them.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.candidates.models import Candidate
        from apps.candidates.services import create_candidate
        from apps.documents.models import CandidateDocument
        from apps.documents.services import complete_upload, receive_upload, request_upload
        from document_ai.pdf import make_pdf

        if not settings.DEBUG:
            raise CommandError("seed_candidates only runs with DEBUG on.")
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            raise CommandError(f"No tenant {options['tenant']!r}. Run seed_users first.")
        recruiters = [
            m.user
            for m in Membership.objects.filter(tenant=tenant, is_active=True).select_related("user")
            if "recruiter" in m.roles or "hr_admin" in m.roles
        ]
        if not recruiters:
            raise CommandError("This tenant has no recruiter or HR admin to record the candidates.")
        # Recruiters see talent-pool profiles and the candidates they added; HR admins see everyone.
        demo = [u for u in recruiters if u.username == f"{tenant.slug}_recruiter"]
        if demo and not options["spread"]:
            recruiters = demo

        with tenant_scope(tenant.id):
            existing = set(
                Candidate.objects.filter(external_id__startswith="seed-").values_list("external_id", flat=True)
            )
        created, documents = 0, []
        for i, person in enumerate(build_people(options["count"])):
            if person["external_id"] in existing:
                continue
            ctx = build_execution_context(user_id=recruiters[i % len(recruiters)].pk, requested_tenant_id=tenant.id)
            with tenant_scope(tenant.id):
                candidate = create_candidate(
                    ctx,
                    full_name=person["full_name"],
                    email=person["email"],
                    phone=person["phone"],
                    location=person["location"],
                    source=person["source"],
                    external_id=person["external_id"],
                    application_consent=True,
                    talent_pool_consent=person["talent_pool"],
                    consent_source="careers site form",
                )
                filename = f"{person['full_name'].lower().replace(' ', '_')}_resume.pdf"
                document, link = request_upload(ctx, candidate_id=candidate.id, filename=filename)
                receive_upload(ctx, token=link.url.rstrip("/").split("/")[-1], data=make_pdf(person["lines"]))
            if options["inline"]:
                self._parse_inline(ctx, tenant, document.id)
            else:
                with tenant_scope(tenant.id):
                    complete_upload(ctx, document_id=document.id)  # queues parsing in the worker
            documents.append(document.id)
            created += 1
            if created % 10 == 0:
                self.stdout.write(f"  {created} candidates created")
        self.stdout.write(f"{tenant.name}: {created} new candidates ({len(existing)} were already there).")

        if options["wait"] and documents and not options["inline"]:
            self._wait(tenant, documents, CandidateDocument)
        self.stdout.write(
            self.style.SUCCESS(
                "Done."
                if options["wait"] or options["inline"]
                else "Done. The worker is parsing the resumes now; profiles fill in over a few minutes."
            )
        )

    def _parse_inline(self, ctx: Any, tenant: Tenant, document_id: Any) -> None:
        from unittest import mock

        from agent_engine.runtime import execute_queued
        from apps.documents import services as document_services
        from apps.documents.tasks import process_document

        with tenant_scope(tenant.id), mock.patch.object(document_services, "enqueue_on_commit", lambda *a, **k: None):
            document_services.complete_upload(ctx, document_id=document_id)
        process_document(document_id=str(document_id), tenant_id=str(tenant.id))
        execute_queued(tenant.id)

    def _wait(self, tenant: Tenant, documents: list[Any], model: Any, timeout: int = 1800) -> None:
        from apps.agents.models import AgentRun

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            with tenant_scope(tenant.id):
                done = model.objects.filter(id__in=documents).exclude(status__in=["uploaded", "processing"]).count()
                parsing = AgentRun.objects.filter(kind="resume_parsing", status__in=["queued", "running"]).count()
            self.stdout.write(f"  resumes read: {done}/{len(documents)} · parsing runs still going: {parsing}")
            if done == len(documents) and parsing == 0:
                return
            time.sleep(10)
        self.stdout.write(self.style.WARNING("Stopped waiting; the worker is still busy. Profiles keep filling in."))
