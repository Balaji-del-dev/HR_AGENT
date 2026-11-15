from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.api.mixins import TENANT_HEADER_PARAMETER, TenantViewSet
from apps.approvals.api.views import ApprovalRequestSerializer
from apps.offers import services
from apps.offers.models import Offer, OfferStatusHistory


class OfferHistorySerializer(serializers.ModelSerializer[OfferStatusHistory]):
    actor_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = OfferStatusHistory
        fields = ["from_status", "to_status", "actor_id", "reason", "created_at"]
        read_only_fields = fields


class OfferSerializer(serializers.ModelSerializer[Offer]):
    application_id = serializers.UUIDField(read_only=True)
    candidate_name = serializers.CharField(source="application.candidate.full_name", read_only=True)
    band_min = serializers.DecimalField(source="comp_band.min_salary", max_digits=12, decimal_places=2, read_only=True)
    band_max = serializers.DecimalField(source="comp_band.max_salary", max_digits=12, decimal_places=2, read_only=True)
    status_history = OfferHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id",
            "application_id",
            "candidate_name",
            "title",
            "base_salary",
            "currency",
            "bonus_percent",
            "start_date",
            "rationale",
            "status",
            "band_min",
            "band_max",
            "status_history",
            "created_at",
        ]
        read_only_fields = fields


class OfferCreateIn(serializers.Serializer[Any]):
    application_id = serializers.UUIDField()
    base_salary = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    bonus_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    rationale = serializers.CharField(required=False, allow_blank=True, default="")


class OutcomeIn(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["sent", "accepted", "declined", "withdrawn"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")


@extend_schema(parameters=[TENANT_HEADER_PARAMETER], tags=["offers"])
class OfferViewSet(TenantViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = OfferSerializer
    filterset_fields = ["status", "application"]
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self) -> QuerySet[Offer]:
        if self.is_schema_request:
            return Offer.objects.none()
        return (
            services.visible_offers(self.ctx)
            .select_related("comp_band", "application__candidate")
            .prefetch_related("status_history")
        )

    @extend_schema(request=OfferCreateIn, responses={201: OfferSerializer})
    def create(self, request: Request) -> Response:
        payload = OfferCreateIn(data=request.data)
        payload.is_valid(raise_exception=True)
        offer = services.create_offer_draft(self.ctx, **payload.validated_data)
        return Response(
            OfferSerializer(services.get_visible_offer(self.ctx, offer.id)).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses={201: ApprovalRequestSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str) -> Response:
        approval = services.submit_offer(self.ctx, offer_id=UUID(pk))
        return Response(ApprovalRequestSerializer(approval).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=OutcomeIn, responses=OfferSerializer)
    @action(detail=True, methods=["post"])
    def outcome(self, request: Request, pk: str) -> Response:
        payload = OutcomeIn(data=request.data)
        payload.is_valid(raise_exception=True)
        services.record_outcome(self.ctx, offer_id=UUID(pk), **payload.validated_data)
        return Response(OfferSerializer(services.get_visible_offer(self.ctx, UUID(pk))).data)


router = SimpleRouter()
router.register("offers", OfferViewSet, basename="offer")
urlpatterns = router.urls
