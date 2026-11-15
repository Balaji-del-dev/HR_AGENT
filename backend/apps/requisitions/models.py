from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q

from apps.core.models import TenantScopedModel


class CompBand(TenantScopedModel):
    """Approved pay range for a department and level. Offers must fall inside one."""

    department = models.CharField(max_length=120)
    level = models.CharField(max_length=40)
    currency = models.CharField(max_length=3, default="INR")
    min_salary = models.DecimalField(max_digits=12, decimal_places=2)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["department", "level"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "department", "level"], name="compband_unique_department_level"),
            models.CheckConstraint(condition=Q(min_salary__lte=F("max_salary")), name="compband_min_lte_max"),
            models.CheckConstraint(condition=Q(min_salary__gt=0), name="compband_min_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.department} {self.level} ({self.currency} {self.min_salary}-{self.max_salary})"


class JobRequisition(TenantScopedModel):
    """A request to hire, owned by one tenant. HR admins approve it through the approvals app."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CLOSED = "closed", "Closed"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full time"
        PART_TIME = "part_time", "Part time"
        CONTRACT = "contract", "Contract"
        INTERN = "intern", "Intern"

    title = models.CharField(max_length=200)
    department = models.CharField(max_length=120)
    location = models.CharField(max_length=120, blank=True)
    level = models.CharField(max_length=40, blank=True)
    employment_type = models.CharField(max_length=16, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    headcount = models.PositiveSmallIntegerField(default=1)
    summary = models.TextField(blank=True, help_text="Why the role exists and what success looks like.")
    must_have_skills = ArrayField(models.CharField(max_length=80), default=list, blank=True)
    nice_to_have_skills = ArrayField(models.CharField(max_length=80), default=list, blank=True)
    comp_band = models.ForeignKey(CompBand, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    hiring_manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status"], name="requisition_tenant_status")]
        constraints = [
            models.CheckConstraint(condition=Q(headcount__gte=1), name="requisition_headcount_positive"),
        ]

    def __str__(self) -> str:
        return self.title


class RequisitionAssignment(TenantScopedModel):
    """A recruiter assigned to a requisition: the object-level grant for recruiters.

    An explicit tenant-scoped table rather than django-guardian rows, so the
    grant itself sits under Row-Level Security (see docs/adr/0002).
    """

    requisition = models.ForeignKey(JobRequisition, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["requisition", "user"], name="assignment_unique_requisition_user"),
        ]
