from rest_framework.routers import SimpleRouter

from apps.applications.api.views import ApplicationViewSet

router = SimpleRouter()
router.register("applications", ApplicationViewSet, basename="application")
urlpatterns = router.urls
