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
    distribution_preview,
    confirm_distribution,
    forecast_compare_methods,
    doctor_me_view,
    doctor_schedules_view,
    doctor_studies_view,
    doctor_study_status_view,
    admin_notifications_view,
    login_view,
    profile_view,
    change_password_view,
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
    path('distribute/', distribute_studies_view, name='distribute-studies'),
    path('distribute/confirm/', confirm_distribution, name='confirm-distribution'),
    path('distribute/preview/', distribution_preview, name='distribution-preview'),
    path('forecast/compare-methods/', forecast_compare_methods, name='forecast-compare-methods'),
    path("doctor/me/", doctor_me_view, name="doctor-me"),
    path("doctor/schedules/", doctor_schedules_view, name="doctor-schedules"),
    path("doctor/studies/", doctor_studies_view, name="doctor-studies"),
    path("doctor/studies/<str:research_number>/status/", doctor_study_status_view, name="doctor-study-status"),
    path("notifications/", admin_notifications_view, name="admin-notifications"),
    path('auth/login/', login_view, name="auth-login"),
    path("auth/profile/", profile_view, name="auth-profile"),
    path("auth/change-password/", change_password_view, name="auth-change-password"),
]
