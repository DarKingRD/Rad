from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DoctorViewSet,
    StudyTypeViewSet,
    ScheduleViewSet,
    StudyViewSet,
    dashboard_stats,
    chart_data,
    distribute_studies_view,
    distribution_preview
)

router = DefaultRouter()
router.register(r"doctors", DoctorViewSet, basename="doctor")
router.register(r"study-types", StudyTypeViewSet, basename="study-type")
router.register(r"schedules", ScheduleViewSet, basename="schedule")
router.register(r"studies", StudyViewSet, basename="study")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/stats/", dashboard_stats, name="dashboard-stats"),
    path("dashboard/chart/", chart_data, name="chart-data"),
    path("distribute/", distribute_studies_view, name='distribute'),
    path("distribute/preview/", distribution_preview, name="distribution-preview")
]
