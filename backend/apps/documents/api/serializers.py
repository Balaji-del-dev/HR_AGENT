from rest_framework import serializers

from apps.documents.models import CandidateDocument, DocumentSpan


class DocumentSerializer(serializers.ModelSerializer[CandidateDocument]):
    candidate_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CandidateDocument
        fields = [
            "id",
            "candidate_id",
            "kind",
            "original_name",
            "detected_content_type",
            "size_bytes",
            "status",
            "page_count",
            "ocr_used",
            "sanitizer_flags",
            "injection_suspected",
            "error",
            "processed_at",
            "created_at",
        ]
        read_only_fields = fields


class SpanSerializer(serializers.ModelSerializer[DocumentSpan]):
    class Meta:
        model = DocumentSpan
        fields = ["span_id", "page", "start", "end", "section", "text", "text_masked", "flags", "position"]
        read_only_fields = fields


class SignedLinkOut(serializers.Serializer[object]):
    url = serializers.CharField()
    expires_in = serializers.IntegerField()
