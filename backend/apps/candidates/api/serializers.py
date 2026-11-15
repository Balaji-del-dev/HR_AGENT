from typing import Any

from rest_framework import serializers

from apps.candidates.models import (
    Candidate,
    CandidateCertification,
    CandidateConsent,
    CandidateEducation,
    CandidateExperience,
    CandidateProfile,
    CandidateSkill,
)
from apps.documents.api.serializers import DocumentSerializer

FACT_BASE = ["id", "evidence", "confidence", "needs_review", "reviewed_at", "document_id"]


class SkillSerializer(serializers.ModelSerializer[CandidateSkill]):
    document_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CandidateSkill
        fields = [*FACT_BASE, "name", "years"]
        read_only_fields = fields


class ExperienceSerializer(serializers.ModelSerializer[CandidateExperience]):
    document_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CandidateExperience
        fields = [*FACT_BASE, "title", "organization", "start", "end", "summary"]
        read_only_fields = fields


class EducationSerializer(serializers.ModelSerializer[CandidateEducation]):
    document_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CandidateEducation
        fields = [*FACT_BASE, "degree", "institution", "field_of_study", "year"]
        read_only_fields = fields


class CertificationSerializer(serializers.ModelSerializer[CandidateCertification]):
    document_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CandidateCertification
        fields = [*FACT_BASE, "name", "issuer", "year"]
        read_only_fields = fields


class ConsentSerializer(serializers.ModelSerializer[CandidateConsent]):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = CandidateConsent
        fields = ["purpose", "granted", "granted_at", "withdrawn_at", "source", "is_active"]
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer[CandidateProfile]):
    class Meta:
        model = CandidateProfile
        fields = ["missing_sections", "extracted_at"]
        read_only_fields = fields


CONTACT_FIELDS = ("email", "phone", "location")


class CandidateSerializer(serializers.ModelSerializer[Candidate]):
    """Contact details are shown only to recruiters and HR admins (field-level permission)."""

    class Meta:
        model = Candidate
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "location",
            "source",
            "in_talent_pool",
            "is_anonymized",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance: Candidate) -> dict[str, Any]:
        data: dict[str, Any] = super().to_representation(instance)
        ctx = self.context.get("ctx")
        if ctx is None or not ctx.has_role("hr_admin", "recruiter"):
            for field in CONTACT_FIELDS:
                if data.get(field):
                    data[field] = ""
        return data


class CandidateDetailSerializer(CandidateSerializer):
    consents = ConsentSerializer(many=True, read_only=True)
    profile = ProfileSerializer(read_only=True, allow_null=True)
    skills = SkillSerializer(many=True, read_only=True)
    experience = ExperienceSerializer(many=True, read_only=True)
    education = EducationSerializer(many=True, read_only=True)
    certifications = CertificationSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta(CandidateSerializer.Meta):
        fields = [
            *CandidateSerializer.Meta.fields,
            "consents",
            "profile",
            "skills",
            "experience",
            "education",
            "certifications",
            "documents",
        ]
        read_only_fields = fields


class CandidateCreateIn(serializers.Serializer[Any]):
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    location = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    source = serializers.ChoiceField(  # type: ignore[assignment]
        choices=Candidate.Source.choices, default=Candidate.Source.APPLIED
    )
    application_consent = serializers.BooleanField(default=True)
    talent_pool_consent = serializers.BooleanField(default=False)
    consent_source = serializers.CharField(max_length=120, required=False, default="recorded by recruiter")


class ConsentIn(serializers.Serializer[Any]):
    purpose = serializers.ChoiceField(choices=CandidateConsent.Purpose.choices)
    granted = serializers.BooleanField()
    source = serializers.CharField(  # type: ignore[assignment]
        max_length=120, required=False, allow_blank=True, default=""
    )


class FactCorrectionIn(serializers.Serializer[Any]):
    changes = serializers.DictField()


class UploadUrlIn(serializers.Serializer[Any]):
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    size_bytes = serializers.IntegerField(min_value=0, required=False, default=0)


class UploadUrlOut(serializers.Serializer[Any]):
    document_id = serializers.UUIDField()
    upload_url = serializers.CharField()
    expires_in = serializers.IntegerField()


class ReviewQueueOut(serializers.Serializer[Any]):
    skills = SkillSerializer(many=True)
    experience = ExperienceSerializer(many=True)
    education = EducationSerializer(many=True)
    certifications = CertificationSerializer(many=True)
