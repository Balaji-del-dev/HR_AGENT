from django.urls import path

from apps.documents.api.views import (
    DocumentCompleteView,
    DocumentDetailView,
    DocumentDownloadUrlView,
    DocumentSpansView,
    DownloadView,
    UploadView,
)

urlpatterns = [
    path("documents/<uuid:document_id>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<uuid:document_id>/complete/", DocumentCompleteView.as_view(), name="document-complete"),
    path("documents/<uuid:document_id>/spans/", DocumentSpansView.as_view(), name="document-spans"),
    path("documents/<uuid:document_id>/download-url/", DocumentDownloadUrlView.as_view(), name="document-download-url"),
    path("uploads/<str:token>/", UploadView.as_view(), name="document-upload"),
    path("downloads/<str:token>/", DownloadView.as_view(), name="document-download"),
]
