from rest_framework import serializers

from apps.matching.models import CriterionResult, MatchingAssessment, RecruiterDecision


class CriterionResultSerializer(serializers.ModelSerializer[CriterionResult]):
    requirement_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = CriterionResult
        fields = [
            "id",
            "requirement_id",
            "criterion",
            "level",
            "status",
            "model_status",
            "evidence",
            "rejected_evidence",
            "validation_note",
            "question",
            "position",
        ]
        read_only_fields = fields


class AssessmentSerializer(serializers.ModelSerializer[MatchingAssessment]):
    application_id = serializers.UUIDField(read_only=True)
    candidate_id = serializers.UUIDField(read_only=True)
    requisition_id = serializers.UUIDField(read_only=True)
    job_description_id = serializers.UUIDField(read_only=True)
    agent_run_id = serializers.UUIDField(read_only=True, allow_null=True)
    job_description_version = serializers.IntegerField(source="job_description.version", read_only=True)
    criteria = CriterionResultSerializer(many=True, read_only=True)

    class Meta:
        model = MatchingAssessment
        fields = [
            "id",
            "application_id",
            "candidate_id",
            "requisition_id",
            "job_description_id",
            "job_description_version",
            "agent_run_id",
            "status",
            "prompt_version",
            "model_name",
            "graph_version",
            "summary",
            "criteria",
            "created_at",
        ]
        read_only_fields = fields


class RecruiterDecisionSerializer(serializers.ModelSerializer[RecruiterDecision]):
    actor_id = serializers.UUIDField(read_only=True)
    assessment_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = RecruiterDecision
        fields = ["id", "decision", "from_stage", "to_stage", "reason", "actor_id", "assessment_id", "created_at"]
        read_only_fields = fields
