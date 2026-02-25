from rest_framework import viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Q
from .models import Doctor, StudyType, Schedule, Study
from .serializers import (
    DoctorSerializer,
    DoctorWithLoadSerializer,
    StudyTypeSerializer,
    ScheduleSerializer,
    ScheduleWithDoctorSerializer,
    StudySerializer,
    StudyWithDetailsSerializer,
    DashboardStatsSerializer,
    ChartDataSerializer,
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .services.distribution import distribute_studies


class DoctorViewSet(viewsets.ModelViewSet):
    queryset = Doctor.objects.all()
    serializer_class = DoctorSerializer
    pagination_class = None

    def get_queryset(self):
        # Для списка показываем всех врачей, можно фильтровать по is_active
        queryset = Doctor.objects.all()
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        return queryset

    @action(detail=False, methods=["get"])
    def with_load(self, request):
        """Врачи с текущей загрузкой ЗА ТЕКУЩИЙ МЕСЯЦ"""
        from django.utils import timezone
        from datetime import datetime

        # Получаем первый и последний день текущего месяца
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Последний день месяца
        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1)

        doctors = Doctor.objects.all()  # ← Убрали фильтр is_active

        data = []
        for doctor in doctors:
            # Считаем ТОЛЬКО неподписанные исследования ЗА ТЕКУЩИЙ МЕСЯЦ
            active_studies = Study.objects.filter(
                diagnostician=doctor,
                created_at__gte=month_start,
                created_at__lt=month_end,
                status__in=["confirmed", "pending"],  # ← НЕ считаем signed
            ).count()

            # Расчёт нагрузки: количество исследований * средний УП (1.5)
            current_load = int(active_studies * 1.5)

            data.append(
                {
                    "id": doctor.id,
                    "fio_alias": doctor.fio_alias or f"Врач {doctor.id}",
                    "position_type": doctor.position_type,
                    "max_up_per_day": doctor.max_up_per_day or 120,
                    "is_active": (
                        doctor.is_active if doctor.is_active is not None else True
                    ),
                    "specialty": (
                        "Рентгенолог"
                        if doctor.position_type == "radiologist"
                        else "КТ-диагност"
                    ),
                    "current_load": round(current_load, 1),
                    "max_load": doctor.max_up_per_day or 120,
                    "active_studies": active_studies,
                }
            )

        return Response(data)


class StudyTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StudyType.objects.all()
    serializer_class = StudyTypeSerializer


class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.all().select_related("doctor")
    serializer_class = ScheduleSerializer
    pagination_class = None
    filterset_fields = ["doctor_id", "work_date", "is_day_off"]

    def get_queryset(self):
        queryset = Schedule.objects.all().select_related("doctor")
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
        """Расписание на конкретную дату"""
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
        queryset = Study.objects.all().select_related("study_type", "diagnostician")
        status = self.request.query_params.get("status")
        priority = self.request.query_params.get("priority")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if status:
            queryset = queryset.filter(status=status)
        if priority:
            queryset = queryset.filter(priority=priority)
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return queryset

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Ожидающие исследования (без врача)"""
        studies = (
            Study.objects.filter(diagnostician_id__isnull=True)
            .select_related("study_type", "diagnostician")
            .order_by("-created_at")
        )
        serializer = StudyWithDetailsSerializer(studies, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def cito(self, request):
        """CITO исследования"""
        studies = Study.objects.filter(priority="cito").select_related(
            "study_type", "diagnostician"
        )[:100]
        serializer = StudyWithDetailsSerializer(studies, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def asap(self, request):
        """ASAP исследования"""
        studies = Study.objects.filter(priority="asap").select_related(
            "study_type", "diagnostician"
        )[:100]
        serializer = StudyWithDetailsSerializer(studies, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Назначить исследование врачу"""
        study = self.get_object()
        doctor_id = request.data.get("doctor_id")

        if not doctor_id:
            return Response({"error": "doctor_id required"}, status=400)

        study.diagnostician_id = doctor_id
        study.status = "confirmed"
        study.save()

        return Response({"status": "assigned", "doctor_id": doctor_id})

    @action(detail=True, methods=["put"])
    def update_status(self, request, pk=None):
        """Обновить статус исследования"""
        study = self.get_object()
        new_status = request.data.get("status")

        if new_status:
            study.status = new_status
            study.save()

        return Response({"status": study.status})

    def get_serializer_class(self):
        if self.action in ["list", "retrieve", "pending", "cito", "asap"]:
            return StudyWithDetailsSerializer
        return StudySerializer


@api_view(["GET"])
def dashboard_stats(request):
    """Статистика для дашборда ЗА ТЕКУЩИЙ МЕСЯЦ"""
    from django.utils import timezone
    from datetime import datetime

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Фильтр по месяцу (если не передана конкретная дата)
    date = request.query_params.get("date")
    if date:
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            studies_qs = Study.objects.filter(created_at__date=date_obj)
        except ValueError:
            studies_qs = Study.objects.filter(created_at__gte=month_start)
    else:
        studies_qs = Study.objects.filter(created_at__gte=month_start)

    total_studies = studies_qs.count()

    # Signed не считаем в pending
    completed_studies = studies_qs.filter(status="signed").count()
    pending_studies = studies_qs.filter(
        status__in=["confirmed", "pending"], diagnostician_id__isnull=False
    ).count()

    # Врачи которые были активны в этом месяце
    active_doctors = (
        Doctor.objects.filter(studies__created_at__gte=month_start).distinct().count()
    )

    cito_studies = studies_qs.filter(priority="cito").count()
    asap_studies = studies_qs.filter(priority="asap").count()

    avg_load = 0
    if active_doctors > 0:
        avg_load = int(pending_studies / active_doctors * 1.5)
    else:
        avg_load = 0

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
    """Данные для графиков ЗА ТЕКУЩИЙ МЕСЯЦ"""
    from django.utils import timezone
    from datetime import datetime, timedelta

    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")

    # Если даты не переданы — берём текущий месяц
    if not date_from or not date_to:
        now = timezone.now()
        date_from_obj = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        date_to_obj = now
    else:
        try:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            now = timezone.now()
            date_from_obj = now.replace(day=1)
            date_to_obj = now

    data = []
    current_date = date_from_obj
    while current_date <= date_to_obj:
        studies = Study.objects.filter(created_at__date=current_date)

        # План — все исследования за день
        plan = studies.count()

        # Факт — только подписанные
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


@api_view(["GET", "POST"])  # ← Было ['POST'], стало ['GET', 'POST']
def distribute_studies_view(request):
    """Автоматическое распределение исследований по врачам"""
    if request.method == "POST":
        try:
            result = distribute_studies()
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": str(e), "message": "Ошибка при распределении исследований"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    else:  # GET
        # Предварительный просмотр без выполнения
        from api.models import Study, Doctor, Schedule
        from django.utils import timezone

        pending = Study.objects.filter(
            diagnostician__isnull=True
        ).count()
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
                "message": "Отправьте POST-запрос для запуска распределения",
            }
        )


@api_view(["GET"])
def distribution_preview(request):
    """
    Предварительный просмотр распределения (без сохранения).

    Request: GET /api/distribute/preview/
    Response: {
        'pending_studies': 50,
        'available_doctors': 12,
        'estimated_tardiness': 15.3
    }
    """
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
            "message": "Готов к распределению"
            if pending > 0 and doctors > 0
            else "Нет данных",
        }
    )
