from datetime import datetime, timedelta
import uuid
from django.utils import timezone
from django.core.cache import cache
from django.db.models import (
    Case,
    F,
    IntegerField,
    Min,
    Max,
    Sum,
    When,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Doctor, Study, StudyType, Schedule
from .serializers import (
    ChartDataSerializer,
    DashboardStatsSerializer,
    DoctorSerializer,
    ScheduleSerializer,
    ScheduleWithDoctorSerializer,
    StudySerializer,
    StudyWithDetailsSerializer,
    StudyTypeSerializer,
)


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

        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1)

        # Считаем рабочие дни в текущем месяце (пн–пт)
        working_days_in_month = sum(
            1 for i in range((month_end.date() - month_start.date()).days)
            if (month_start.date() + timedelta(days=i)).weekday() < 5
        )

        doctors = Doctor.objects.all()

        data = []
        for doctor in doctors:
            up_data = Study.objects.filter(
                diagnostician=doctor,
                created_at__gte=month_start,
                created_at__lt=month_end,
                status__in=["confirmed", "pending", "signed"],
            ).aggregate(
                total_up=Sum(F("study_type__up_value")),
                active_count=Sum(
                    Case(
                        When(status__in=["confirmed", "pending"], then=1),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
            )

            current_load = round(up_data["total_up"] or 0, 3)
            active_studies = up_data["active_count"] or 0

            # Дневной лимит из модели, fallback по должности
            daily_limit = doctor.max_up_per_day or (
                6 if doctor.position_type == "head" else 8
            )

            # Месячная норма = дневной лимит × рабочие дни месяца
            monthly_norm = 50 

            data.append(
                {
                    "id": doctor.id,
                    "fio_alias": doctor.fio_alias or f"Врач {doctor.id}",
                    "position_type": doctor.position_type,
                    "max_up_per_day": daily_limit,
                    "is_active": (
                        doctor.is_active if doctor.is_active is not None else True
                    ),
                    "specialty": (
                        "Рентгенолог"
                        if doctor.position_type == "radiologist"
                        else "КТ-диагност"
                    ),
                    "modality": doctor.modality or [],
                    "current_load": current_load,
                    "max_load": monthly_norm,
                    "active_studies": active_studies,
                    "load_percentage": (
                        round((current_load / monthly_norm) * 100, 1)
                        if monthly_norm > 0 else 0
                    ),
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

    completed_studies = studies_qs.filter(status="signed").count()
    # pending — исследования без назначенного врача (реальная очередь)
    pending_studies = studies_qs.filter(diagnostician_id__isnull=True).count()

    # Врачи которые были активны в этом месяце
    active_doctors = (
        Doctor.objects.filter(studies__created_at__gte=month_start).distinct().count()
    )

    cito_studies = studies_qs.filter(priority="cito").count()
    asap_studies = studies_qs.filter(priority="asap").count()

    # Средняя нагрузка: сумма УП по всем исследованиям / количество активных врачей
    if active_doctors > 0:
        total_up = studies_qs.filter(
            diagnostician_id__isnull=False
        ).aggregate(
            total=Sum(F("study_type__up_value"))
        )["total"] or 0
        avg_load = int(total_up / active_doctors)
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


@api_view(["GET", "POST"])
def distribute_studies_view(request):
    """
    Распределение исследований с поддержкой:
    - Выбора даты
    - Режима предпросмотра
    - Фильтрации по периоду создания исследований
    """
    if request.method == "POST":
        # Получаем параметры
        target_date_str = request.data.get("date")
        preview = request.data.get("preview", True)  # По умолчанию превью
        date_from_str = request.data.get("date_from")
        date_to_str = request.data.get("date_to")
        use_mip = request.data.get("use_mip", True)

        # Парсим дату распределения
        target_date = None
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
                    status=400,
                )

        # Парсим период исследований
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
            from .services.distribution import DistributionService

            service = DistributionService(target_date=target_date)
            service.set_preview_mode(preview)

            result = service.distribute(
                use_mip=use_mip, date_from=date_from, date_to=date_to
            )

            # Если это превью - сохраняем результат во временное хранилище
            if preview:
                distribution_id = str(uuid.uuid4())
                cache.set(
                    f"distribution_preview_{distribution_id}",
                    result,
                    timeout=3600,  # 1 час
                )
                result["distribution_id"] = distribution_id
                result["message"] = (
                    "Предварительное распределение выполнено. Отправьте POST на /api/distribute/confirm/ для сохранения."
                )

            return Response(result, status=200)

        except Exception as e:
            return Response(
                {"error": str(e), "message": "Ошибка при распределении исследований"},
                status=500,
            )

    else:  # GET - информация о доступных данных
        # Получаем диапазон доступных дат с исследованиями
        date_range = Study.objects.aggregate(
            min_date=Min("created_at__date"),
            max_date=Max("created_at__date"),
        )

        # Получаем диапазон дат с расписаниями врачей
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
    """
    Подтверждение и сохранение распределения в БД.
    Request: POST /api/distribute/confirm/
    Body: {"distribution_id": "uuid-из-превью"}
    """
    distribution_id = request.data.get("distribution_id")

    if not distribution_id:
        return Response({"error": "distribution_id обязателен"}, status=400)

    # Получаем сохранённое превью
    preview_data = cache.get(f"distribution_preview_{distribution_id}")

    if not preview_data:
        return Response(
            {"error": "Распределение не найдено или истекло время (1 час)"}, status=404
        )

    try:
        from .services.distribution import DistributionService
        from .models import Study

        # Повторно выполняем распределение, но уже с сохранением
        target_date_str = preview_data.get("target_date")
        target_date = None
        if target_date_str:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        service = DistributionService(target_date=target_date)
        service.set_preview_mode(False)  # Теперь сохраняем

        # Получаем assignments из превью и сохраняем
        assignments = preview_data.get("assignments", [])
        assignment_dict = {a["study_id"]: a["doctor_id"] for a in assignments}

        # Сохраняем в БД (PK у Study — research_number, не id)
        for study_id, doc_id in assignment_dict.items():
            Study.objects.filter(research_number=study_id).update(
                diagnostician_id=doc_id, status="confirmed"
            )

        # Очищаем кэш
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
    """
    Быстрый превью без выполнения распределения.
    Показывает сколько исследований и врачей доступно на дату.
    """
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
