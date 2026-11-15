from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.models import ApplicationStageHistory, JobApplication
from apps.matching.api.serializers import RecruiterDecisionSerializer
from apps.matching.models import RecruiterDecision


class StageHistorySerializer(serializers.ModelSerializer[ApplicationStageHistory]):
    actor_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ApplicationStageHistory
        fields = ["id", "from_stage", "to_stage", "actor_id", "reason", "created_at"]
        read_only_fields = fields


class ApplicationSerializer(serializers.ModelSerializer[JobApplication]):
    requisition_id = serializers.UUIDField(read_only=True)
    requisition_title = serializers.CharField(source="requisition.title", read_only=True)
    candidate_id = serializers.UUIDField(read_only=True)
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "requisition_id",
            "requisition_title",
            "candidate_id",
            "candidate_name",
            "stage",
            "source",
            "stage_changed_at",
            "created_at",
        ]
        read_only_fields = fields


class ApplicationDetailSerializer(ApplicationSerializer):
    stage_history = StageHistorySerializer(many=True, read_only=True)
    decisions = serializers.SerializerMethodField()

    class Meta(ApplicationSerializer.Meta):
        fields = [*ApplicationSerializer.Meta.fields, "stage_history", "decisions"]
        read_only_fields = fields

    @extend_schema_field(RecruiterDecisionSerializer(many=True))
    def get_decisions(self, obj: JobApplication) -> list[dict[str, Any]]:
        decisions = RecruiterDecision.objects.filter(application=obj).order_by("-created_at")
        return RecruiterDecisionSerializer(decisions, many=True).data  # type: ignore[return-value]


class ApplicationCreateIn(serializers.Serializer[Any]):
    requisition_id = serializers.UUIDField()
    candidate_id = serializers.UUIDField()
    source = serializers.CharField(  # type: ignore[assignment]
        max_length=40, required=False, allow_blank=True, default=""
    )


class DecisionIn(serializers.Serializer[Any]):
    decision = serializers.ChoiceField(choices=RecruiterDecision.Decision.choices)
    reason = serializers.CharField(max_length=4000)
    to_stage = serializers.ChoiceField(choices=JobApplication.Stage.choices, required=False)
    assessment_id = serializers.UUIDField(required=False, allow_null=True)


class ReasonIn(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=4000)


class CommsRunIn(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=["outreach", "update", "decline"])
    template_key = serializers.CharField(required=False, allow_blank=True, default="")
    instructions = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
