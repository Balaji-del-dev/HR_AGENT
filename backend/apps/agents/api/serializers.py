from typing import Any

from rest_framework import serializers

from apps.agents.models import AgentRun, AgentStep, AssistantThread, ToolCall


class AgentStepSerializer(serializers.ModelSerializer[AgentStep]):
    class Meta:
        model = AgentStep
        fields = ["sequence", "node", "summary", "created_at"]
        read_only_fields = fields


class ToolCallSerializer(serializers.ModelSerializer[ToolCall]):
    class Meta:
        model = ToolCall
        fields = [
            "id",
            "tool",
            "agent",
            "status",
            "policy_reason",
            "result_summary",
            "error",
            "duration_ms",
            "created_at",
        ]
        read_only_fields = fields


class AgentRunSerializer(serializers.ModelSerializer[AgentRun]):
    requested_by_id = serializers.UUIDField(read_only=True)
    requisition_id = serializers.UUIDField(read_only=True, allow_null=True)
    thread_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = AgentRun
        fields = [
            "id",
            "kind",
            "status",
            "requested_by_id",
            "requisition_id",
            "thread_id",
            "input",
            "output",
            "pending_interrupt",
            "graph_version",
            "prompt_versions",
            "model_name",
            "tokens_in",
            "tokens_out",
            "tool_call_count",
            "guard_flags",
            "error",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentRunDetailSerializer(AgentRunSerializer):
    steps = AgentStepSerializer(many=True, read_only=True)
    tool_calls = ToolCallSerializer(many=True, read_only=True)

    class Meta(AgentRunSerializer.Meta):
        fields = [*AgentRunSerializer.Meta.fields, "steps", "tool_calls"]
        read_only_fields = fields


class StartRunIn(serializers.Serializer[Any]):
    """Optional instructions for runs that accept them."""

    instructions = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ResumeIn(serializers.Serializer[Any]):
    approval_request_id = serializers.UUIDField()
    decision = serializers.ChoiceField(choices=["approve", "reject", "request_changes"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)
    edits = serializers.DictField(required=False, default=dict)


class AssistantMessageIn(serializers.Serializer[Any]):
    message = serializers.CharField(max_length=4000)
    thread_id = serializers.UUIDField(required=False, allow_null=True)


class AssistantThreadSerializer(serializers.ModelSerializer[AssistantThread]):
    class Meta:
        model = AssistantThread
        fields = ["id", "title", "created_at", "updated_at"]
        read_only_fields = fields


class RunKindIn(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=AgentRun.Kind.choices)
    params = serializers.DictField()
