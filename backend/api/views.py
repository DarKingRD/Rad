from datetime import datetime, timedelta
import logging
import uuid

from django.core.cache import cache
from django.contrib.auth.models import User
from django.db.models import Case, Count, IntegerField, Max, Min, Q, Sum, When
from django.db.models.functions import TruncMonth
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Doctor, Schedule, Study, StudyType
from .serializers import (
    ChartDataSerializer,
    DashboardStatsSerializer,
    DistributionConfirmSerializer,
    DistributionInfoSerializer,
    DistributionPreviewInfoSerializer,
    DistributionRunSerializer,
    DoctorSerializer,
    DoctorWithLoadSerializer,
    ScheduleSerializer,
    ScheduleWithDoctorSerializer,
    ShiftForecastQuerySerializer,
    ShiftForecastResponseSerializer,
    ForecastCompareQuerySerializer,
    StudyAssignSerializer,
    StudySerializer,
    StudyStatusUpdateSerializer,
    StudyWithDetailsSerializer,
    StudyTypeSerializer,
)
from .services.doctor_queries import get_doctors_with_load_context
from .services.modality_catalog import DISPLAY_MODALITIES
from .services.study_queries import (
    get_pending_studies_queryset,
    get_priority_studies_queryset,
)
from .services.dashboard_queries import (
    get_chart_data,
    get_dashboard_stats_data,
    parse_dashboard_range,
)
from .services.distribution_api import (
    confirm_distribution_result,
    get_distribution_info,
    get_distribution_preview_info,
    parse_distribution_date,
    parse_distribution_datetime_end,
    parse_distribution_datetime_start,
    run_distribution,
)
from .services.shift_forecast_multi_method import (
    FORECAST_COMPARE_METHODS,
    FORECAST_METHODS,
    build_shift_forecast,
    evaluate_forecast_methods,
)

logger = logging.getLogger(__name__)
DOCTOR_LOGIN_PREFIX = "doctor_" # подредачить!
ADMIN_NOTIFICATIONS_CACHE_KEY = "admin_notifications"
ADMIN_NOTIFICATIONS_LIMIT = 50


def _resolve_doctor_from_username(username):
    if not username:
        return None

    normalized = username.strip().lower()
    doctor_id_part = None
    if normalized.startswith(DOCTOR_LOGIN_PREFIX):
        doctor_id_part = normalized.removeprefix(DOCTOR_LOGIN_PREFIX)
    elif normalized.isdigit():
        doctor_id_part = normalized

    if not doctor_id_part or not doctor_id_part.isdigit():
        return None

    return Doctor.objects.filter(id=int(doctor_id_part), is_active=True).first()


def _get_user_doctor(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_staff or user.is_superuser:
        return None
    return _resolve_doctor_from_username(user.username)


def _build_user_payload(user):
    doctor = _get_user_doctor(user)
    payload = {
        "id": user.id,
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "role": "doctor" if doctor else "manager",
        "doctor_id": doctor.id if doctor else None,
        "doctor_name": doctor.fio_alias if doctor else None,
    }
    return payload


def _authenticate_doctor_default(username, password):
    doctor = _resolve_doctor_from_username(username)
    if not doctor:
        return None

    allowed_passwords = {username, f"{DOCTOR_LOGIN_PREFIX}{doctor.id}"}
    if password not in allowed_passwords:
        return None

    user, created = User.objects.get_or_create(
        username=f"{DOCTOR_LOGIN_PREFIX}{doctor.id}",
        defaults={
            "first_name": doctor.fio_alias or f"Врач {doctor.id}",
            "is_staff": False,
            "is_superuser": False,
        },
    )
    if created or not user.has_usable_password():
        user.set_password(password)
        user.save(update_fields=["password"])
    return authenticate(username=user.username, password=password)


def _doctor_required_response(request):
    doctor = _get_user_doctor(request.user)
    if doctor is None:
        return None, Response(
            {"detail": "Раздел доступен только врачу."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return doctor, None


def _study_up_sum(queryset):
    value = queryset.aggregate(total=Sum("study_type__up_value"))["total"] or 0
    return round(float(value), 3)


def _build_doctor_period_stats(doctor, start_dt, end_dt):
    qs = Study.objects.filter(
        diagnostician=doctor,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    )
    completed_qs = qs.filter(status="signed")
    return {
        "assigned": qs.count(),
        "completed": completed_qs.count(),
        "pending": qs.filter(status="confirmed").count(),
        "completed_up": _study_up_sum(completed_qs),
    }


def _month_bounds(year, month):
    start = timezone.make_aware(datetime(year, month, 1))
    if month == 12:
        end = timezone.make_aware(datetime(year + 1, 1, 1))
    else:
        end = timezone.make_aware(datetime(year, month + 1, 1))
    return start, end


def _doctor_statistics_payload(doctor):
    today = timezone.localdate()
    today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    tomorrow_start = today_start + timedelta(days=1)
    month_start, next_month_start = _month_bounds(today.year, today.month)

    previous_months_qs = (
        Study.objects.filter(
            diagnostician=doctor,
            created_at__lt=month_start,
            created_at__isnull=False,
        )
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            assigned=Count("research_number"),
            completed=Count("research_number", filter=Q(status="signed")),
            pending=Count("research_number", filter=Q(status="confirmed")),
            completed_up=Sum("study_type__up_value", filter=Q(status="signed")),
        )
        .order_by("-month")[:6]
    )

    previous_months = [
        {
            "month": item["month"].date().isoformat() if item["month"] else None,
            "assigned": item["assigned"],
            "completed": item["completed"],
            "pending": item["pending"],
            "completed_up": round(float(item["completed_up"] or 0), 3),
        }
        for item in previous_months_qs
    ]

    return {
        "today": _build_doctor_period_stats(doctor, today_start, tomorrow_start),
        "current_month": _build_doctor_period_stats(doctor, month_start, next_month_start),
        "previous_months": previous_months,
    }


def _get_admin_notifications():
    return cache.get(ADMIN_NOTIFICATIONS_CACHE_KEY, [])


def _set_admin_notifications(notifications):
    cache.set(
        ADMIN_NOTIFICATIONS_CACHE_KEY,
        notifications[:ADMIN_NOTIFICATIONS_LIMIT],
        timeout=None,
    )


def _push_admin_notification(message, notification_type="study_completed", payload=None):
    notification = {
        "id": str(uuid.uuid4()),
        "type": notification_type,
        "message": message,
        "created_at": timezone.now().isoformat(),
        "payload": payload or {},
    }
    notifications = [notification, *_get_admin_notifications()]
    _set_admin_notifications(notifications)
    return notification


class DoctorViewSet(viewsets.ModelViewSet):
    queryset = Doctor.objects.all()
    serializer_class = DoctorSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        return queryset

    @action(detail=False, methods=["get"])
    def with_load(self, request):
        """Врачи с текущей загрузкой за текущий месяц + расписание на сегодня."""
        doctors_qs, today_schedules = get_doctors_with_load_context()

        serializer = DoctorWithLoadSerializer(
            doctors_qs,
            many=True,
            context={"today_schedules": today_schedules},
        )
        return Response(serializer.data)


class StudyTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StudyType.objects.all()
    serializer_class = StudyTypeSerializer


class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.all().select_related("doctor")
    serializer_class = ScheduleSerializer
    pagination_class = None
    filterset_fields = ["doctor_id", "work_date", "is_day_off"]

    def get_queryset(self):
        queryset = super().get_queryset()
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        doctor_id = self.request.query_params.get("doctor_id")
        is_active_doctor = self.request.query_params.get("is_active_doctor")

        if date_from:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(work_date__lte=date_to)
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)
        if is_active_doctor:
            queryset = queryset.filter(doctor__is_active=True)

        return queryset

    @action(detail=False, methods=["get"])
    def by_date(self, request):
        date = request.query_params.get("date")
        if not date:
            return Response({"error": "Date parameter required"}, status=400)

        schedules = Schedule.objects.filter(
            work_date=date, is_day_off=0
        ).select_related("doctor")
        serializer = ScheduleWithDoctorSerializer(schedules, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def forecast(self, request):
        """
        Прогноз входящего потока исследований и потребности во врачах по выбранному диапазону дат.
        """
        query_serializer = ShiftForecastQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        validated = query_serializer.validated_data
        result = build_shift_forecast(
            date_from=validated.get("date_from"),
            date_to=validated.get("date_to"),
            method=validated.get("method", "weekday_mean"),
            recent_weeks=validated.get("recent_weeks", 4),
            moving_window_days=validated.get("moving_window_days", 14),
            history_start_override=validated.get("history_start_date"),
            history_end_override=validated.get("history_end_date"),
        )
        serializer = ShiftForecastResponseSerializer(result)
        return Response(serializer.data)


class StudyViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = None
    queryset = Study.objects.all().select_related("study_type", "diagnostician")
    serializer_class = StudySerializer
    filterset_fields = ["status", "priority", "diagnostician_id"]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        priority = self.request.query_params.get("priority")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        diagnostician_id = self.request.query_params.get("diagnostician_id")

        if status_param:
            queryset = queryset.filter(status=status_param)
        if priority:
            queryset = queryset.filter(priority=priority)
        if diagnostician_id:
            queryset = queryset.filter(diagnostician_id=diagnostician_id)
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return queryset

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Ожидающие исследования (без назначенного врача) с пагинацией."""
        page_size = min(int(request.query_params.get("page_size", 100)), 500)
        page = max(int(request.query_params.get("page", 1)), 1)
        offset = (page - 1) * page_size

        priority = request.query_params.get("priority")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        modality = request.query_params.get("modality")

        qs = get_pending_studies_queryset(
            priority=priority or None,
            date_from=date_from or None,
            date_to=date_to or None,
            modality=modality or None,
        )

        total = qs.count()
        studies = qs[offset : offset + page_size]
        serializer = StudyWithDetailsSerializer(studies, many=True)

        return Response(
            {
                "results": serializer.data,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        )

    @action(detail=False, methods=["get"])
    def cito(self, request):
        """CITO исследования."""
        limit = min(int(request.query_params.get("limit", 100)), 500)
        studies = get_priority_studies_queryset("cito")[:limit]
        serializer = StudyWithDetailsSerializer(studies, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def asap(self, request):
        """ASAP исследования."""
        limit = min(int(request.query_params.get("limit", 100)), 500)
        studies = get_priority_studies_queryset("asap")[:limit]
        serializer = StudyWithDetailsSerializer(studies, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Назначить исследование врачу."""
        study = self.get_object()

        input_serializer = StudyAssignSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        doctor_id = input_serializer.validated_data["doctor_id"]

        study.diagnostician_id = doctor_id
        study.status = "confirmed"
        study.save(update_fields=["diagnostician_id", "status"])

        output_serializer = StudyWithDetailsSerializer(
            study,
            context=self.get_serializer_context(),
        )
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["put", "patch"])
    def update_status(self, request, pk=None):
        """Обновить статус исследования."""
        study = self.get_object()

        input_serializer = StudyStatusUpdateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        new_status = input_serializer.validated_data["status"]
        study.status = new_status

        if new_status == "pending":
            study.diagnostician_id = None
            study.save(update_fields=["status", "diagnostician_id"])
        else:
            study.save(update_fields=["status"])

        output_serializer = StudyWithDetailsSerializer(
            study,
            context=self.get_serializer_context(),
        )
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "pending", "cito", "asap"]:
            return StudyWithDetailsSerializer
        return StudySerializer


@api_view(["GET"])
def dashboard_stats(request):
    """
    Статистика для дашборда за период date_from/date_to.
    Если даты не переданы — берём текущий месяц.
    """
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    include_all = request.query_params.get("all_dates") in {"1", "true", "True"}

    try:
        start_dt, end_dt = parse_dashboard_range(date_from, date_to, include_all=include_all)
    except ValueError:
        return Response(
            {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
            status=400,
        )

    data = get_dashboard_stats_data(start_dt, end_dt)
    serializer = DashboardStatsSerializer(data)
    return Response(serializer.data)


@api_view(["GET"])
def chart_data(request):
    """
    Данные для графиков за период date_from/date_to.
    Если даты не переданы — берём текущий месяц.
    """
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    include_all = request.query_params.get("all_dates") in {"1", "true", "True"}

    try:
        start_dt, end_dt = parse_dashboard_range(date_from, date_to, include_all=include_all)
    except ValueError:
        return Response(
            {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
            status=400,
        )

    start_date = start_dt.date()
    end_date = end_dt.date() if end_dt.time() != datetime.min.time() else end_dt.date()

    # Так как parse_dashboard_range для переданного date_to возвращает exclusive end_dt (+1 day),
    # для графика нужно вернуть последний реальный день периода.
    if date_from and date_to:
        end_date = (end_dt - timedelta(days=1)).date()
    elif include_all:
        end_date = (end_dt - timedelta(days=1)).date()

    if start_date > end_date:
        return Response(
            {"error": "date_from не может быть позже date_to"},
            status=400,
        )

    data = get_chart_data(start_date, end_date)
    serializer = ChartDataSerializer(data, many=True)
    return Response(serializer.data)


@api_view(["GET", "POST"])
def distribute_studies_view(request):
    """
    GET  -> служебная информация для экрана распределения
    POST -> запуск распределения / preview
    """
    if request.method == "GET":
        data = get_distribution_info()
        serializer = DistributionInfoSerializer(data)
        return Response(serializer.data)

    input_serializer = DistributionRunSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)

    validated = input_serializer.validated_data

    target_date = validated.get("date")
    preview = validated.get("preview", True)
    date_from = validated.get("date_from")
    date_to = validated.get("date_to")
    use_mip = validated.get("use_mip", True)
    objective = validated.get("objective", "weighted_tardiness_lexicographic")

    date_from_dt = parse_distribution_datetime_start(
        date_from.isoformat() if date_from else None
    )
    date_to_dt = parse_distribution_datetime_end(
        date_to.isoformat() if date_to else None
    )

    try:
        result = run_distribution(
            target_date=target_date,
            preview=preview,
            date_from=date_from_dt,
            date_to=date_to_dt,
            use_mip=use_mip,
            objective=objective,
        )
        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {
                "error": str(e),
                "message": "Ошибка при распределении исследований",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def confirm_distribution(request):
    """
    Подтверждение preview-распределения и сохранение в БД.
    """
    input_serializer = DistributionConfirmSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)

    distribution_id = input_serializer.validated_data["distribution_id"]

    try:
        result = confirm_distribution_result(distribution_id)
        if result is None:
            return Response(
                {"error": "Распределение не найдено или истекло время (1 час)"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {
                "error": str(e),
                "message": "Ошибка при сохранении распределения",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def distribution_preview(request):
    """
    Быстрый preview без запуска алгоритма.
    """
    date_str = request.query_params.get("date")

    try:
        target_date = parse_distribution_date(date_str) if date_str else timezone.now().date()
    except ValueError:
        return Response(
            {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = get_distribution_preview_info(target_date)
    serializer = DistributionPreviewInfoSerializer(data)
    return Response(serializer.data)


@api_view(["GET"])
def forecast_compare_methods(request):
    """
    Сравнение методов прогнозирования на holdout-периоде.

    По умолчанию оцениваем последнюю неделю истории, а обучаем методы только
    на данных до этой недели.
    """
    query_serializer = ForecastCompareQuerySerializer(data=request.query_params)
    query_serializer.is_valid(raise_exception=True)

    validated = query_serializer.validated_data
    methods = validated.get("methods") or None

    try:
        result = evaluate_forecast_methods(
            methods=methods,
            evaluation_start_date=validated.get("evaluation_start_date"),
            evaluation_end_date=validated.get("evaluation_end_date"),
            evaluation_days=validated.get("evaluation_days", 7),
            recent_weeks=validated.get("recent_weeks", 4),
            moving_window_days=validated.get("moving_window_days", 14),
            min_train_days=validated.get("min_train_days", 21),
        )
    except ValueError as exc:
        logger.warning("Forecast comparison validation failed", exc_info=True)
        return Response(
            {"detail": "Invalid forecast comparison parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    response_payload = {
        **result,
        "available_methods": [
            {"key": key, "label": FORECAST_METHODS[key]}
            for key in FORECAST_COMPARE_METHODS
        ],
        "params": {
            "methods": methods or list(FORECAST_COMPARE_METHODS),
            "evaluation_start_date": (
                validated["evaluation_start_date"].isoformat()
                if validated.get("evaluation_start_date")
                else None
            ),
            "evaluation_end_date": (
                validated["evaluation_end_date"].isoformat()
                if validated.get("evaluation_end_date")
                else None
            ),
            "evaluation_days": validated.get("evaluation_days", 7),
            "recent_weeks": validated.get("recent_weeks", 4),
            "moving_window_days": validated.get("moving_window_days", 14),
            "min_train_days": validated.get("min_train_days", 21),
        },
    }
    return Response(response_payload)


@api_view(["GET", "PATCH"])
def doctor_me_view(request):
    doctor, error_response = _doctor_required_response(request)
    if error_response:
        return error_response

    if request.method == "PATCH":
        if "modality" not in request.data:
            return Response(
                {"detail": "Передайте список modality."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = DoctorSerializer(
            doctor,
            data={"modality": request.data.get("modality")},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

    return Response(
        {
            "doctor": DoctorSerializer(doctor).data,
            "stats": _doctor_statistics_payload(doctor),
            "available_modalities": DISPLAY_MODALITIES,
        }
    )


@api_view(["GET"])
def doctor_schedules_view(request):
    doctor, error_response = _doctor_required_response(request)
    if error_response:
        return error_response

    today = timezone.localdate()
    date_from = request.query_params.get("date_from") or today.isoformat()
    date_to = request.query_params.get("date_to") or (today + timedelta(days=14)).isoformat()

    schedules = Schedule.objects.filter(
        doctor=doctor,
        work_date__gte=date_from,
        work_date__lte=date_to,
    ).order_by("work_date", "time_start")
    serializer = ScheduleSerializer(schedules, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def doctor_studies_view(request):
    doctor, error_response = _doctor_required_response(request)
    if error_response:
        return error_response

    qs = Study.objects.filter(diagnostician=doctor).select_related(
        "study_type",
        "diagnostician",
    )

    status_param = request.query_params.get("status")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")

    if status_param:
        statuses = [item.strip() for item in status_param.split(",") if item.strip()]
        qs = qs.filter(status__in=statuses)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    qs = qs.order_by(
        Case(
            When(priority="cito", then=0),
            When(priority="asap", then=1),
            default=2,
            output_field=IntegerField(),
        ),
        "created_at",
    )
    serializer = StudyWithDetailsSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["PATCH", "PUT"])
def doctor_study_status_view(request, research_number):
    doctor, error_response = _doctor_required_response(request)
    if error_response:
        return error_response

    study = Study.objects.filter(
        research_number=research_number,
        diagnostician=doctor,
    ).select_related("study_type", "diagnostician").first()
    if study is None:
        return Response(
            {"detail": "Исследование не найдено среди назначений врача."},
            status=status.HTTP_404_NOT_FOUND,
        )

    input_serializer = StudyStatusUpdateSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    new_status = input_serializer.validated_data["status"]
    if new_status not in {"signed", "pending", "confirmed"}:
        return Response(
            {"detail": "Врач может отметить исследование выполненным или отказаться от него."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    study.status = new_status
    if new_status == "pending":
        doctor_name = doctor.fio_alias or f"Врач {doctor.id}"
        study_type_name = study.study_type.name if study.study_type else None
        message = f"{doctor_name} отказался от исследования {study.research_number}"
        if study_type_name:
            message = f"{message}: {study_type_name}"
        study.diagnostician = None
        study.save(update_fields=["status", "diagnostician"])
        _push_admin_notification(
            message,
            notification_type="study_refused",
            payload={
                "doctor_id": doctor.id,
                "doctor_name": doctor_name,
                "research_number": study.research_number,
                "study_type": study_type_name,
            },
        )
    else:
        study.save(update_fields=["status"])
        if new_status == "signed":
            doctor_name = doctor.fio_alias or f"Врач {doctor.id}"
            study_type_name = study.study_type.name if study.study_type else None
            message = f"{doctor_name} выполнил исследование {study.research_number}"
            if study_type_name:
                message = f"{message}: {study_type_name}"
            _push_admin_notification(
                message,
                payload={
                    "doctor_id": doctor.id,
                    "doctor_name": doctor_name,
                    "research_number": study.research_number,
                    "study_type": study_type_name,
                },
            )
    return Response(StudyWithDetailsSerializer(study).data, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
def admin_notifications_view(request):
    if request.method == "POST":
        action = request.data.get("action")
        if action == "clear":
            _set_admin_notifications([])
            return Response({"notifications": [], "unread_count": 0})
        return Response(
            {"detail": "Неизвестное действие."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    notifications = _get_admin_notifications()
    return Response(
        {
            "notifications": notifications,
            "unread_count": len(notifications),
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response({"detail": "Введите логин и пароль."}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)
    if user is None:
        user = _authenticate_doctor_default(username, password)
    if user is None:
        return Response({"detail": "Неверные учетные данные."}, status=status.HTTP_401_UNAUTHORIZED)

    token, _ = Token.objects.get_or_create(user=user)
    return Response(
        {
            "token": token.key,
            "user": _build_user_payload(user),
        }
    )

@api_view(["GET", "PATCH"])
def profile_view(request):
    user = request.user

    if request.method == "GET":
        return Response(
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                **_build_user_payload(user),
            }
        )

    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")

    update_fields = []
    if first_name is not None:
        user.first_name = str(first_name).strip()
        update_fields.append("first_name")
    if last_name is not None:
        user.last_name = str(last_name).strip()
        update_fields.append("last_name")

    if not update_fields:
        return Response(
            {"detail": "Передайте first_name и/или last_name."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.save(update_fields=update_fields)
    return Response(
        {
            "first_name": user.first_name,
            "last_name": user.last_name,
            **_build_user_payload(user),
        }
    )


@api_view(["POST"])
def change_password_view(request):
    old_password = request.data.get("old_password")
    new_password = request.data.get("new_password")

    if not old_password or not new_password:
        return Response(
            {"detail": "Передайте old_password и new_password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    if not user.check_password(old_password):
        return Response(
            {"detail": "Старый пароль указан неверно."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response({"detail": "Пароль успешно изменён."})
