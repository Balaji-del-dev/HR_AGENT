from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import TenantScopedModel


class CandidateDocument(TenantScopedModel):
    """A file a candidate supplied. The bytes live in object storage, not here."""

    class Kind(models.TextChoices):
        RESUME = "resume", "Resume"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING_UPLOAD = "pending_upload", "Waiting for upload"
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        REJECTED = "rejected", "Rejected (type, size or format)"
        QUARANTINED = "quarantined", "Quarantined (failed malware scan)"
        FAILED = "failed", "Failed"

    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.RESUME)
    original_name = models.CharField(max_length=255)
    declared_content_type = models.CharField(max_length=120, blank=True)
    detected_content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    storage_key = models.CharField(max_length=400)
    bucket = models.CharField(max_length=20, default="quarantine")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING_UPLOAD)
    page_count = models.PositiveSmallIntegerField(default=0)
    ocr_used = models.BooleanField(default=False)
    sanitizer_flags = models.JSONField(default=list, blank=True)
    injection_suspected = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_name

    @property
    def short_id(self) -> str:
        return self.id.hex[:8]


class DocumentSpan(TenantScopedModel):
    """A line of resume text with a stable id: document, page and character offsets.

    ``text`` is what the resume says; ``text_masked`` is what a model may see.
    An empty ``text_masked`` means the line is withheld from models entirely
    (for example a date of birth or a gender marker).
    """

    document = models.ForeignKey(CandidateDocument, on_delete=models.CASCADE, related_name="spans")
    span_id = models.CharField(max_length=80)
    page = models.PositiveSmallIntegerField()
    start = models.PositiveIntegerField()
    end = models.PositiveIntegerField()
    section = models.CharField(max_length=40, blank=True)
    text = models.TextField()
    text_masked = models.TextField(blank=True)
    flags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["document", "position"]
        constraints = [
            models.UniqueConstraint(fields=["document", "span_id"], name="span_unique_document_span_id"),
        ]


class ResumeChunk(TenantScopedModel):
    """Masked text from consecutive spans of one section, embedded for evidence search.

    ``embedding`` is a plain float array so the schema works on any PostgreSQL.
    With pgvector installed, an HNSW expression index over ``embedding::vector``
    speeds up search (see apps.documents.vector).
    """

    document = models.ForeignKey(CandidateDocument, on_delete=models.CASCADE, related_name="chunks")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE, related_name="chunks")
    section = models.CharField(max_length=40, blank=True)
    span_ids = ArrayField(models.CharField(max_length=80))
    content_masked = models.TextField()
    embedding = ArrayField(models.FloatField(), null=True, blank=True)
    embedding_model = models.CharField(max_length=80, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["document", "position"]
