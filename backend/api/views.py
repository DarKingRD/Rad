from datetime import datetime, timedelta
import uuid

from django.core.cache import cache
from django.db.models import Case, F, IntegerField, Max, Min, Sum, When
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Doctor, Schedule, Study, StudyType
from .serializers import (
    ChartDataSerializer,
    DashboardStatsSerializer,
    DoctorSerializer,
    DoctorWithLoadSerializer,
    ScheduleSerializer,
    ScheduleWithDoctorSerializer,
    StudyAssignSerializer,
    StudySerializer,
    StudyStatusUpdateSerializer,
    StudyWithDetailsSerializer,
    StudyTypeSerializer,
)
from .services.distribution import DistributionService
from .services.doctor_queries import get_doctors_with_load_context
from .services.study_queries import (
    get_pending_studies_queryset,
    get_priority_studies_queryset,
)


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

        if status_param:
            queryset = queryset.filter(status=status_param)
        if priority:
            queryset = queryset.filter(priority=priority)
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

        qs = get_pending_studies_queryset()

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

    if not date_from or not date_to:
        now = timezone.now()
        date_from_obj = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        date_to_obj = now
    else:
        try:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            return Response(
                {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
                status=400,
            )

    studies_qs = Study.objects.filter(
        created_at__gte=date_from_obj,
        created_at__lt=date_to_obj,
    )

    total_studies = studies_qs.count()
    completed_studies = studies_qs.filter(status="signed").count()
    pending_studies = studies_qs.filter(diagnostician_id__isnull=True).count()

    active_doctors = (
        Doctor.objects.filter(
            studies__created_at__gte=date_from_obj,
            studies__created_at__lt=date_to_obj,
        )
        .distinct()
        .count()
    )

    cito_studies = studies_qs.filter(priority="cito").count()
    asap_studies = studies_qs.filter(priority="asap").count()

    total_up = (
        studies_qs.filter(diagnostician_id__isnull=False)
        .aggregate(total=Sum(F("study_type__up_value")))
        .get("total")
        or 0
    )

    avg_load = int(total_up / active_doctors) if active_doctors > 0 else 0

    data = {
        "total_studies": total_studies,
        "completed_studies": completed_studies,
        "pending_studies": pending_studies,
        "active_doctors": active_doctors,
        "avg_load_per_doctor": avg_load,
        "cito_studies": cito_studies,
        "asap_studies": asap_studies,
    }

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

    if not date_from or not date_to:
        now = timezone.now()
        start_date = now.replace(day=1).date()
        end_date = now.date()
    else:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
                status=400,
            )

    if start_date > end_date:
        return Response(
            {"error": "date_from не может быть позже date_to"},
            status=400,
        )

    data = []
    current_date = start_date

    while current_date <= end_date:
        studies = Study.objects.filter(created_at__date=current_date)

        plan = studies.count()
        actual = studies.filter(status="signed").count()

        data.append(
            {
                "name": current_date.strftime("%d.%m"),
                "plan": plan,
                "actual": actual,
            }
        )

        current_date += timedelta(days=1)

    serializer = ChartDataSerializer(data, many=True)
    return Response(serializer.data)


@api_view(["GET", "POST"])
def distribute_studies_view(request):
    """
    Распределение исследований с поддержкой:
    - Выбора даты
    - Режима предпросмотра
    - Фильтрации по периоду создания исследований
    """
    if request.method == "POST":
        target_date_str = request.data.get("date")
        preview = request.data.get("preview", True)
        date_from_str = request.data.get("date_from")
        date_to_str = request.data.get("date_to")
        use_mip = request.data.get("use_mip", True)

        target_date = None
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
                    status=400,
                )

        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
            except ValueError:
                return Response({"error": "Неверный формат date_from"}, status=400)
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, "%Y-%m-%d")
            except ValueError:
                return Response({"error": "Неверный формат date_to"}, status=400)

        try:
            service = DistributionService(target_date=target_date)
            service.set_preview_mode(preview)

            result = service.distribute(
                use_mip=use_mip, date_from=date_from, date_to=date_to
            )

            if preview:
                distribution_id = str(uuid.uuid4())
                cache.set(
                    f"distribution_preview_{distribution_id}",
                    result,
                    timeout=3600,
                )
                result["distribution_id"] = distribution_id
                result["message"] = (
                    "Предварительное распределение выполнено. "
                    "Отправьте POST на /api/distribute/confirm/ для сохранения."
                )

            return Response(result, status=200)

        except Exception as e:
            return Response(
                {"error": str(e), "message": "Ошибка при распределении исследований"},
                status=500,
            )

    date_range = Study.objects.aggregate(
        min_date=Min("created_at__date"),
        max_date=Max("created_at__date"),
    )

    schedule_range = Schedule.objects.aggregate(
        min_date=Min("work_date"), max_date=Max("work_date")
    )

    pending = Study.objects.filter(diagnostician__isnull=True).count()
    today = timezone.now().date()

    doctors = (
        Doctor.objects.filter(
            is_active=True, schedule__work_date=today, schedule__is_day_off=0
        )
        .distinct()
        .count()
    )

    return Response(
        {
            "pending_studies": pending,
            "available_doctors": doctors,
            "study_date_range": {
                "min": date_range["min_date"].isoformat()
                if date_range["min_date"]
                else None,
                "max": date_range["max_date"].isoformat()
                if date_range["max_date"]
                else None,
            },
            "schedule_date_range": {
                "min": schedule_range["min_date"].isoformat()
                if schedule_range["min_date"]
                else None,
                "max": schedule_range["max_date"].isoformat()
                if schedule_range["max_date"]
                else None,
            },
            "message": "Отправьте POST-запрос с параметром date для распределения",
        }
    )


@api_view(["POST"])
def confirm_distribution(request):
    distribution_id = request.data.get("distribution_id")

    if not distribution_id:
        return Response({"error": "distribution_id обязателен"}, status=400)

    preview_data = cache.get(f"distribution_preview_{distribution_id}")

    if not preview_data:
        return Response(
            {"error": "Распределение не найдено или истекло время (1 час)"},
            status=404,
        )

    try:
        from .models import Study

        target_date_str = preview_data.get("target_date")
        target_date = None
        if target_date_str:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        service = DistributionService(target_date=target_date)
        service.set_preview_mode(False)

        assignments = preview_data.get("assignments", [])
        assignment_dict = {
            a.get("study_number"): a["doctor_id"]
            for a in assignments
            if a.get("study_number")
        }

        for study_id, doc_id in assignment_dict.items():
            Study.objects.filter(research_number=study_id).update(
                diagnostician_id=doc_id, status="confirmed"
            )

        cache.delete(f"distribution_preview_{distribution_id}")

        return Response(
            {
                "status": "confirmed",
                "assigned": len(assignment_dict),
                "distribution_id": distribution_id,
                "message": f"Успешно сохранено {len(assignment_dict)} назначений",
            }
        )

    except Exception as e:
        return Response(
            {"error": str(e), "message": "Ошибка при сохранении распределения"},
            status=500,
        )


@api_view(["GET"])
def distribution_preview(request):
    date_str = request.query_params.get("date")

    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Неверный формат даты"}, status=400)
    else:
        target_date = timezone.now().date()

    pending = Study.objects.filter(
        diagnostician__isnull=True, created_at__date__lte=target_date
    ).count()

    doctors = (
        Doctor.objects.filter(
            is_active=True, schedule__work_date=target_date, schedule__is_day_off=0
        )
        .distinct()
        .count()
    )

    return Response(
        {
            "pending_studies": pending,
            "available_doctors": doctors,
            "target_date": target_date.isoformat(),
            "message": "Готов к распределению"
            if pending > 0 and doctors > 0
            else "Нет данных",
        }
    )
