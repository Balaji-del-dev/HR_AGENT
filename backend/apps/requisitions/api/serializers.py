"""Requisition API shapes. tenant_id is never accepted or shown: it comes from the request context."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.requisitions.models import CompBand, JobRequisition, RequisitionAssignment


class CompBandSerializer(serializers.ModelSerializer[CompBand]):
    class Meta:
        model = CompBand
        fields = ["id", "department", "level", "currency", "min_salary", "max_salary", "is_active"]
        read_only_fields = ["id", "is_active"]


class RequisitionSerializer(serializers.ModelSerializer[JobRequisition]):
    hiring_manager_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    comp_band_id = serializers.UUIDField(read_only=True, allow_null=True)
    assigned_recruiter_ids = serializers.SerializerMethodField()

    class Meta:
        model = JobRequisition
        fields = [
            "id",
            "title",
            "department",
            "location",
            "level",
            "employment_type",
            "headcount",
            "summary",
            "must_have_skills",
            "nice_to_have_skills",
            "comp_band_id",
            "status",
            "hiring_manager_id",
            "created_by_id",
            "assigned_recruiter_ids",
            "submitted_at",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_assigned_recruiter_ids(self, obj: JobRequisition) -> list[UUID]:
        return [assignment.user_id for assignment in obj.assignments.all()]


class RequisitionCreateSerializer(serializers.Serializer[dict[str, Any]]):
    title = serializers.CharField(max_length=200)
    department = serializers.CharField(max_length=120)
    location = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    level = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    employment_type = serializers.ChoiceField(
        choices=JobRequisition.EmploymentType.choices, default=JobRequisition.EmploymentType.FULL_TIME
    )
    headcount = serializers.IntegerField(min_value=1, max_value=1000, default=1)
    summary = serializers.CharField(required=False, allow_blank=True, default="", max_length=5000)
    must_have_skills = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, default=list, max_length=30
    )
    nice_to_have_skills = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, default=list, max_length=30
    )
    comp_band_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    hiring_manager_id = serializers.UUIDField()


class RequisitionUpdateSerializer(RequisitionCreateSerializer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.default = serializers.empty


class RecruiterAssignmentCreateSerializer(serializers.Serializer[dict[str, Any]]):
    recruiter_id = serializers.UUIDField()


class RequisitionAssignmentSerializer(serializers.ModelSerializer[RequisitionAssignment]):
    requisition_id = serializers.UUIDField(read_only=True)
    user_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RequisitionAssignment
        fields = ["id", "requisition_id", "user_id", "created_at"]
        read_only_fields = fields


class CloseIn(serializers.Serializer[dict[str, Any]]):
    reason = serializers.CharField(max_length=2000)


class ImportApplicantsIn(serializers.Serializer[dict[str, Any]]):
    csv = serializers.CharField(max_length=2_000_000)


class ImportApplicantsOut(serializers.Serializer[dict[str, Any]]):
    created = serializers.IntegerField()
    existing = serializers.IntegerField()
    skipped_no_consent = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())  # type: ignore[assignment]
