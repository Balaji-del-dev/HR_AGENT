import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import Membership, User
from apps.core.management.commands.reset_data import _tables_to_clear
from apps.core.management.commands.seed_users import PEOPLE
from apps.core.models import Tenant

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=True)
def test_seed_users_creates_people_for_every_role_and_can_run_again():
    call_command("seed_users")
    call_command("seed_users")  # a second run changes nothing

    expected = sum(len(people) for _, people in PEOPLE.values())
    assert User.objects.count() == expected
    assert Membership.objects.count() == expected
    assert set(Tenant.objects.values_list("slug", flat=True)) == {"acme", "globex"}

    acme = Tenant.objects.get(slug="acme")
    roles = [r for m in Membership.objects.filter(tenant=acme) for r in m.roles]
    assert roles.count("recruiter") >= 5
    assert {"hr_admin", "recruiter", "hiring_manager", "interviewer", "finance_approver", "auditor"} <= set(roles)

    # The sign-in page's demo buttons still work.
    for username in (
        "acme_recruiter",
        "acme_hr_admin",
        "acme_manager",
        "acme_interviewer",
        "acme_finance",
        "acme_auditor",
    ):
        assert User.objects.get(username=username).check_password("demo-pass-2026")


def test_reset_keeps_people_and_clears_hiring_data():
    tables = _tables_to_clear(keep_settings=False)
    for kept in ("accounts_user", "accounts_membership", "core_tenant", "accounts_user_groups", "agents_promptversion"):
        assert kept not in tables
    for cleared in (
        "requisitions_jobrequisition",
        "candidates_candidate",
        "governance_auditevent",
        "agents_agentrun",
        "documents_candidatedocument",
        "requisitions_compband",
    ):
        assert cleared in tables
    assert "requisitions_compband" not in _tables_to_clear(keep_settings=True)


def test_generated_candidates_are_stable_unique_and_parseable():
    from apps.core.management.commands.seed_candidates import TRACKS, build_people
    from document_ai.segmentation import heading_section
    from document_ai.vocabulary import TECH_TERMS

    people = build_people(100)
    assert people == build_people(100)  # same seed, same people
    assert len({p["full_name"] for p in people}) == len({p["email"] for p in people}) == 100
    assert all(skill.lower() in TECH_TERMS for track in TRACKS for skill in track.skills)
    for person in people:
        headings = {heading_section(line) for line in person["lines"]} - {None}
        assert {"experience", "skills"} <= headings
