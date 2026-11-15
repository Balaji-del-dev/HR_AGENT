from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.interviews.models import Interview, InterviewSlot, Scorecard


class SlotSerializer(serializers.ModelSerializer[InterviewSlot]):
    class Meta:
        model = InterviewSlot
        fields = ["id", "start", "end", "status"]
        read_only_fields = fields


class InterviewSerializer(serializers.ModelSerializer[Interview]):
    application_id = serializers.UUIDField(read_only=True)
    candidate_name = serializers.CharField(source="application.candidate.full_name", read_only=True)
    requisition_title = serializers.CharField(source="application.requisition.title", read_only=True)
    panel_user_ids = serializers.SerializerMethodField()
    slots = SlotSerializer(many=True, read_only=True)

    class Meta:
        model = Interview
        fields = [
            "id",
            "application_id",
            "candidate_name",
            "requisition_title",
            "title",
            "round",
            "duration_minutes",
            "status",
            "scheduled_start",
            "scheduled_end",
            "location",
            "panel_user_ids",
            "slots",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_panel_user_ids(self, obj: Interview) -> list[UUID]:
        return [p.user_id for p in obj.panel.all()]


class InterviewCreateIn(serializers.Serializer[Any]):
    application_id = serializers.UUIDField()
    title = serializers.CharField(max_length=200)
    panel_user_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=10)
    round = serializers.IntegerField(min_value=1, max_value=20, default=1)
    duration_minutes = serializers.IntegerField(min_value=15, max_value=480, default=60)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ScorecardSerializer(serializers.ModelSerializer[Scorecard]):
    interview_id = serializers.UUIDField(read_only=True)
    interviewer_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Scorecard
        fields = [
            "id",
            "interview_id",
            "interviewer_id",
            "recommendation",
            "ratings",
            "strengths",
            "concerns",
            "notes",
            "submitted_at",
        ]
        read_only_fields = fields


class ScorecardIn(serializers.Serializer[Any]):
    recommendation = serializers.ChoiceField(choices=Scorecard.Recommendation.choices)
    ratings = serializers.DictField(child=serializers.IntegerField(min_value=1, max_value=5))
    strengths = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)
    concerns = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)
