"""The eval gate itself works, and the offline provider clears it (the CI regression floor)."""

import pytest

from evals.runner import run_all

pytestmark = pytest.mark.django_db


def test_all_suites_pass_offline_and_are_recorded() -> None:
    from apps.agents.models import EvalResult

    results = {r.suite: r for r in run_all()}
    failing = {name: (r.metrics, r.details) for name, r in results.items() if not r.passed}
    assert not failing, failing
    assert EvalResult.objects.filter(passed=True).count() == 4
    assert results["fairness"].metrics == {"identical_masked_input": 1.0, "identical_status": 1.0}
