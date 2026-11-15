from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.models import TenantScopedModel


class Candidate(TenantScopedModel):
    """A person who applied or was sourced. Identity fields never reach a matching prompt."""

    class Source(models.TextChoices):
        APPLIED = "applied", "Applied"
        REFERRAL = "referral", "Referral"
        SOURCED = "sourced", "Sourced"
        TALENT_POOL = "talent_pool", "Talent pool"
        ATS_IMPORT = "ats_import", "ATS import"

    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.APPLIED)
    external_id = models.CharField(max_length=120, blank=True, help_text="Id in the source ATS.")
    in_talent_pool = models.BooleanField(default=False)
    is_anonymized = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "email"], condition=~Q(email=""), name="candidate_unique_tenant_email"
            ),
        ]

    def __str__(self) -> str:
        return self.full_name


class CandidateConsent(TenantScopedModel):
    """Consent per purpose. Withdrawing it stops processing for that purpose."""

    class Purpose(models.TextChoices):
        APPLICATION = "application", "This application"
        TALENT_POOL = "talent_pool", "Talent pool"

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="consents")
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    granted = models.BooleanField(default=True)
    granted_at = models.DateTimeField()
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=120, blank=True, help_text="Where consent was captured.")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["candidate", "purpose"], name="consent_unique_candidate_purpose"),
        ]

    @property
    def is_active(self) -> bool:
        return self.granted and self.withdrawn_at is None


class CandidateProfile(TenantScopedModel):
    """Summary of the latest extraction for a candidate."""

    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name="profile")
    missing_sections = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    extracted_at = models.DateTimeField(null=True, blank=True)
    extraction_run = models.ForeignKey(
        "agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    source_document = models.ForeignKey(
        "documents.CandidateDocument", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )


class EvidenceFact(TenantScopedModel):
    """A fact extracted from a resume. Every fact cites at least one document span."""

    document = models.ForeignKey("documents.CandidateDocument", on_delete=models.CASCADE, related_name="+")
    # [{"span_id": "doc_8f2a:p2:1840-1912", "quote": "..."}]
    evidence = models.JSONField(default=list)
    confidence = models.FloatField(default=1.0)
    needs_review = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    extraction_run = models.ForeignKey(
        "agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        abstract = True


class CandidateSkill(EvidenceFact):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=120)
    years = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["name"]


class CandidateExperience(EvidenceFact):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="experience")
    title = models.CharField(max_length=200)
    organization = models.CharField(max_length=200, blank=True)
    start = models.CharField(max_length=7, blank=True, help_text="YYYY or YYYY-MM")
    end = models.CharField(max_length=7, blank=True, help_text="Blank means current")
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-start"]


class CandidateEducation(EvidenceFact):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="education")
    degree = models.CharField(max_length=200)
    institution = models.CharField(max_length=200, blank=True)
    field_of_study = models.CharField(max_length=200, blank=True)
    year = models.CharField(max_length=4, blank=True)


class CandidateCertification(EvidenceFact):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="certifications")
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200, blank=True)
    year = models.CharField(max_length=4, blank=True)
