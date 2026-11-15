from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.requisitions.api.views import CompBandViewSet, DepartmentsView, RequisitionViewSet

router = SimpleRouter()
router.register("requisitions", RequisitionViewSet, basename="requisition")
router.register("comp-bands", CompBandViewSet, basename="comp-band")

urlpatterns = [path("departments/", DepartmentsView.as_view(), name="departments"), *router.urls]
