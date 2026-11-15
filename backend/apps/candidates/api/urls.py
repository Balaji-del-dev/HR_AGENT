from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.candidates.api.views import CandidateViewSet, FactCorrectionView, ReviewQueueView

router = SimpleRouter()
router.register("candidates", CandidateViewSet, basename="candidate")

urlpatterns = [
    path("candidates/review-queue/", ReviewQueueView.as_view(), name="candidate-review-queue"),
    path("candidates/facts/<str:fact_type>/<uuid:fact_id>/", FactCorrectionView.as_view(), name="candidate-fact"),
    *router.urls,
]
