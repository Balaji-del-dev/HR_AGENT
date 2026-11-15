"""Tenants and people only: several users for every role, and no hiring data.

    python manage.py seed_users

Safe to run again: users are matched by username, and their names, emails and roles
are brought back in line with the lists below. Passwords are set when a user is
created. The original demo logins (acme_recruiter, acme_hr_admin, ...) are kept, so
the sign-in page's demo buttons still work. Local development only.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import Membership, User
from apps.accounts.roles import Role
from apps.core.models import Tenant

DEMO_PASSWORD = "demo-pass-2026"  # noqa: S105 - local demo data only; refused unless DEBUG

HR, REC, HM, INT, FIN, AUD = (
    Role.HR_ADMIN,
    Role.RECRUITER,
    Role.HIRING_MANAGER,
    Role.INTERVIEWER,
    Role.FINANCE_APPROVER,
    Role.AUDITOR,
)

# (username suffix or None for first.last, first name, last name, roles)
PEOPLE: dict[str, tuple[str, list[tuple[str | None, str, str, list[Role]]]]] = {
    "acme": (
        "Acme Corp",
        [
            ("hr_admin", "Hema", "Rao", [HR]),
            ("hr_lead", "Ishaan", "Bose", [HR]),
            (None, "Lakshmi", "Narayanan", [HR]),
            ("recruiter", "Riya", "Sen", [REC]),
            (None, "Kavya", "Menon", [REC, INT]),
            (None, "Arvind", "Krishnan", [REC]),
            (None, "Sneha", "Kulkarni", [REC]),
            (None, "Rahul", "Desai", [REC]),
            (None, "Divya", "Shetty", [REC]),
            (None, "Vikram", "Reddy", [REC]),
            ("manager", "Manoj", "Pillai", [HM]),
            (None, "Nisha", "Kapoor", [HM]),
            (None, "Suresh", "Iyer", [HM, INT]),
            (None, "Ananya", "Das", [HM]),
            (None, "Rohan", "Malhotra", [HM]),
            ("interviewer", "Ira", "Joshi", [INT]),
            (None, "Aditya", "Varma", [INT]),
            (None, "Meera", "Nair", [INT]),
            (None, "Kiran", "Rao", [INT]),
            (None, "Pooja", "Shah", [INT]),
            (None, "Siddharth", "Jain", [INT]),
            (None, "Neha", "Gupta", [INT]),
            (None, "Zoya", "Siddiqui", [INT]),
            (None, "Tarun", "Bhat", [INT]),
            ("finance", "Farhan", "Ali", [FIN]),
            (None, "Deepa", "Raghavan", [FIN]),
            ("auditor", "Anita", "Kapoor", [AUD]),
            (None, "Gautam", "Sharma", [AUD]),
        ],
    ),
    "globex": (
        "Globex",
        [
            ("hr_admin", "Shalini", "Menon", [HR]),
            ("hr_lead", "Prakash", "Gowda", [HR]),
            ("recruiter", "Tanvi", "Arora", [REC]),
            (None, "Naveen", "Kumar", [REC]),
            (None, "Ayesha", "Khan", [REC, INT]),
            ("manager", "Rajesh", "Nambiar", [HM]),
            (None, "Lata", "Krishnan", [HM]),
            ("interviewer", "Varun", "Menon", [INT]),
            (None, "Ishita", "Roy", [INT]),
            (None, "Mohit", "Saxena", [INT]),
            ("finance", "Sunita", "Pai", [FIN]),
            ("auditor", "Devendra", "Patil", [AUD]),
        ],
    ),
}


def username_for(tenant_slug: str, suffix: str | None, first: str, last: str) -> str:
    return f"{tenant_slug}_{suffix}" if suffix else f"{tenant_slug}_{first.lower()}.{last.lower()}"


class Command(BaseCommand):
    help = "Create tenants and users for every role, with no hiring data (local development only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reset-passwords", action="store_true", help="Set every listed user's password again.")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_users only runs with DEBUG on.")
        for slug, (name, people) in PEOPLE.items():
            tenant, _ = Tenant.objects.update_or_create(slug=slug, defaults={"name": name})
            created = 0
            for suffix, first, last, roles in people:
                username = username_for(slug, suffix, first, last)
                email = f"{username}@example.test" if suffix else f"{first.lower()}.{last.lower()}@{slug}.example.test"
                user, new = User.objects.update_or_create(
                    username=username,
                    defaults={"email": email, "first_name": first, "last_name": last, "is_active": True},
                )
                if new or options["reset_passwords"]:
                    user.set_password(DEMO_PASSWORD)
                    user.save(update_fields=["password"])
                    created += int(new)
                Membership.objects.update_or_create(
                    tenant=tenant, user=user, defaults={"roles": [r.value for r in roles], "is_active": True}
                )
            counts: dict[str, int] = {}
            for _, _, _, roles in people:
                for role in roles:
                    counts[role.value] = counts.get(role.value, 0) + 1
            summary = ", ".join(f"{n} {role.replace('_', ' ')}" for role, n in counts.items())
            self.stdout.write(f"{name}: {len(people)} people ({created} new) — {summary}")
        self.stdout.write(self.style.SUCCESS(f"Done. Every user's password is {DEMO_PASSWORD!r}."))
