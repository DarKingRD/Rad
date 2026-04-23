from rest_framework import serializers

from .models import Doctor, Schedule, Study, StudyType
from .services.doctor_queries import (
    MONTHLY_NORM,
    format_time_hhmm,
    get_break_duration_minutes,
    get_daily_limit,
    get_doctor_specialty,
)
from .services.modality_catalog import (
    DISPLAY_MODALITIES,
    OTHER_MODALITY,
    normalize_modality_name,
    sort_modalities,
)
from .services.schedule_status import (
    DAY_STATUS_LABELS,
    get_day_status_label,
    is_day_off_by_status,
    normalize_day_status,
)
from .services.distribution.objectives import OBJECTIVE_REGISTRY
from .services.distribution.config import DEFAULT_SOLVER_BACKEND, SOLVER_BACKEND_CHOICES
from .services.shift_forecast_multi_method import (
    DEFAULT_EVALUATION_DAYS,
    FORECAST_COMPARE_METHODS,
    FORECAST_METHODS,
)


class DoctorSerializer(serializers.ModelSerializer):
    specialty = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            "id",
            "fio_alias",
            "position_type",
            "max_up_per_day",
            "is_active",
            "specialty",
            "modality",
        ]
        read_only_fields = ["id", "specialty"]

    def validate_max_up_per_day(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Максимальное количество УП не может быть отрицательным"
            )
        return value

    def validate_fio_alias(self, value):
        if value and len(value.strip()) < 2:
            raise serializers.ValidationError(
                "ФИО должно содержать минимум 2 символа"
            )
        return value.strip() if value else None

    def validate_modality(self, value):
        if value in (None, ""):
            return []

        if not isinstance(value, (list, tuple)):
            raise serializers.ValidationError(
                "Модальности должны передаваться массивом строк"
            )

        normalized = []
        seen = set()
        invalid = []

        for item in value:
            modality = normalize_modality_name(item)
            if modality == OTHER_MODALITY:
                invalid.append(str(item))
                continue
            if modality not in seen:
                seen.add(modality)
                normalized.append(modality)

        if invalid:
            allowed = ", ".join(DISPLAY_MODALITIES)
            invalid_values = ", ".join(invalid)
            raise serializers.ValidationError(
                f"Неизвестные модальности: {invalid_values}. "
                f"Допустимые значения: {allowed}"
            )

        return sort_modalities(normalized)

    def get_specialty(self, obj):
        return get_doctor_specialty(obj)


class DoctorWithLoadSerializer(DoctorSerializer):
    current_load = serializers.SerializerMethodField()
    max_load = serializers.SerializerMethodField()
    active_studies = serializers.IntegerField(read_only=True, default=0)
    load_percentage = serializers.SerializerMethodField()

    today_shift_start = serializers.SerializerMethodField()
    today_shift_end = serializers.SerializerMethodField()
    today_break_start = serializers.SerializerMethodField()
    today_break_end = serializers.SerializerMethodField()
    today_break_minutes = serializers.SerializerMethodField()

    class Meta(DoctorSerializer.Meta):
        fields = DoctorSerializer.Meta.fields + [
            "current_load",
            "max_load",
            "active_studies",
            "load_percentage",
            "today_shift_start",
            "today_shift_end",
            "today_break_start",
            "today_break_end",
            "today_break_minutes",
        ]

    def _get_schedule(self, obj):
        today_schedules = self.context.get("today_schedules", {})
        return today_schedules.get(obj.id)

    def get_current_load(self, obj):
        value = getattr(obj, "current_load", 0) or 0
        return round(float(value), 3)

    def get_max_load(self, obj):
        return MONTHLY_NORM

    def get_load_percentage(self, obj):
        current_load = self.get_current_load(obj)
        max_load = self.get_max_load(obj)
        return round((current_load / max_load) * 100, 1) if max_load > 0 else 0

    def get_today_shift_start(self, obj):
        schedule = self._get_schedule(obj)
        return format_time_hhmm(schedule.time_start) if schedule else None

    def get_today_shift_end(self, obj):
        schedule = self._get_schedule(obj)
        return format_time_hhmm(schedule.time_end) if schedule else None

    def get_today_break_start(self, obj):
        schedule = self._get_schedule(obj)
        return format_time_hhmm(schedule.break_start) if schedule else None

    def get_today_break_end(self, obj):
        schedule = self._get_schedule(obj)
        return format_time_hhmm(schedule.break_end) if schedule else None

    def get_today_break_minutes(self, obj):
        schedule = self._get_schedule(obj)
        return get_break_duration_minutes(schedule)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["fio_alias"] = instance.fio_alias or f"Врач {instance.id}"
        data["max_up_per_day"] = get_daily_limit(instance)
        data["is_active"] = (
            instance.is_active if instance.is_active is not None else True
        )
        data["modality"] = sort_modalities(instance.modality or [])
        return data


class StudyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyType
        fields = ["id", "name", "modality", "up_value"]


class ScheduleSerializer(serializers.ModelSerializer):
    doctor_id = serializers.PrimaryKeyRelatedField(
        source="doctor",
        queryset=Doctor.objects.all(),
        write_only=True,
        required=False,
    )
    doctor_name = serializers.CharField(source="doctor.fio_alias", read_only=True)
    break_duration_minutes = serializers.SerializerMethodField(read_only=True)
    day_status_label = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "doctor",
            "doctor_id",
            "doctor_name",
            "work_date",
            "time_start",
            "time_end",
            "break_start",
            "break_end",
            "break_duration_minutes",
            "is_day_off",
            "day_status",
            "day_status_label",
            "planned_up",
        ]
        read_only_fields = ["id", "doctor_name", "break_duration_minutes", "day_status_label"]

    def get_break_duration_minutes(self, obj) -> int:
        return get_break_duration_minutes(obj)

    def get_day_status_label(self, obj) -> str:
        return get_day_status_label(getattr(obj, "day_status", 0))

    def validate_planned_up(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Планируемое количество УП не может быть отрицательным"
            )
        return value

    def validate_day_status(self, value):
        status = normalize_day_status(value)
        if status not in DAY_STATUS_LABELS:
            raise serializers.ValidationError("Недопустимое значение day_status")
        return status

    def validate(self, attrs):
        day_status = attrs.get("day_status")
        if day_status is None:
            if "is_day_off" in attrs:
                day_status = 1 if attrs.get("is_day_off") else 0
            elif self.instance is not None:
                day_status = getattr(self.instance, "day_status", 0)
            else:
                day_status = 0
        day_status = normalize_day_status(day_status)
        attrs["day_status"] = day_status
        attrs["is_day_off"] = 1 if is_day_off_by_status(day_status) else 0

        time_start = attrs.get("time_start")
        time_end = attrs.get("time_end")
        break_start = attrs.get("break_start")
        break_end = attrs.get("break_end")

        if time_start and time_end and time_start >= time_end:
            raise serializers.ValidationError(
                "Время окончания работы не может быть раньше или равно времени начала"
            )
        if break_start and break_end and break_start >= break_end:
            raise serializers.ValidationError(
                "Время окончания перерыва не может быть раньше или равно времени начала"
            )
        if break_start and time_start and break_start < time_start:
            raise serializers.ValidationError(
                "Перерыв не может начинаться раньше начала смены"
            )
        if break_end and time_end and break_end > time_end:
            raise serializers.ValidationError(
                "Перерыв не может заканчиваться позже окончания смены"
            )

        if attrs["is_day_off"]:
            attrs["planned_up"] = 0
        return attrs


class ScheduleWithDoctorSerializer(serializers.ModelSerializer):
    doctor = DoctorSerializer(read_only=True)
    break_duration_minutes = serializers.SerializerMethodField(read_only=True)
    day_status_label = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "doctor",
            "work_date",
            "time_start",
            "time_end",
            "break_start",
            "break_end",
            "break_duration_minutes",
            "is_day_off",
            "day_status",
            "day_status_label",
            "planned_up",
        ]

    def get_break_duration_minutes(self, obj) -> int:
        return get_break_duration_minutes(obj)

    def get_day_status_label(self, obj) -> str:
        return get_day_status_label(getattr(obj, "day_status", 0))


class StudySerializer(serializers.ModelSerializer):
    class Meta:
        model = Study
        fields = "__all__"

    def validate_priority(self, value):
        if value not in ["normal", "cito", "asap"]:
            raise serializers.ValidationError("Недопустимое значение приоритета")
        return value


class StudyWithDetailsSerializer(serializers.ModelSerializer):
    study_type = StudyTypeSerializer(read_only=True)
    diagnostician = DoctorSerializer(read_only=True)

    class Meta:
        model = Study
        fields = "__all__"


class StudyAssignSerializer(serializers.Serializer):
    doctor_id = serializers.IntegerField(required=True, min_value=1)

    def validate_doctor_id(self, value):
        if not Doctor.objects.filter(id=value).exists():
            raise serializers.ValidationError("Врач с таким id не найден")
        return value


class StudyStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["pending", "confirmed", "signed"],
        required=True,
    )


class DashboardStatsSerializer(serializers.Serializer):
    total_studies = serializers.IntegerField()
    completed_studies = serializers.IntegerField()
    pending_studies = serializers.IntegerField()
    active_doctors = serializers.IntegerField()
    avg_load_per_doctor = serializers.IntegerField()
    cito_studies = serializers.IntegerField()
    asap_studies = serializers.IntegerField()


class ChartDataSerializer(serializers.Serializer):
    name = serializers.CharField()
    plan = serializers.IntegerField()
    actual = serializers.IntegerField()


class DistributionRangeSerializer(serializers.Serializer):
    min = serializers.CharField(allow_null=True)
    max = serializers.CharField(allow_null=True)


class DistributionInfoSerializer(serializers.Serializer):
    pending_studies = serializers.IntegerField()
    available_doctors = serializers.IntegerField()
    study_date_range = DistributionRangeSerializer()
    schedule_date_range = DistributionRangeSerializer()
    message = serializers.CharField()


class DistributionPreviewInfoSerializer(serializers.Serializer):
    pending_studies = serializers.IntegerField()
    available_doctors = serializers.IntegerField()
    target_date = serializers.CharField()
    message = serializers.CharField()


class DistributionRunSerializer(serializers.Serializer):
    date = serializers.DateField(required=False, allow_null=True)
    preview = serializers.BooleanField(required=False, default=True)
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    use_mip = serializers.BooleanField(required=False, default=True)
    objective = serializers.ChoiceField(
        choices=tuple(OBJECTIVE_REGISTRY.keys()),
        required=False,
        default="weighted_tardiness_lexicographic",
    )
    solver_backend = serializers.ChoiceField(
        choices=SOLVER_BACKEND_CHOICES,
        required=False,
        default=DEFAULT_SOLVER_BACKEND,
    )

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "date_to не может быть раньше date_from"}
            )
        return attrs


class DistributionConfirmSerializer(serializers.Serializer):
    distribution_id = serializers.CharField(required=True)

    def validate_distribution_id(self, value):
        if not value.strip():
            raise serializers.ValidationError("distribution_id обязателен")
        return value.strip()


class ShiftForecastQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    method = serializers.CharField(required=False, default="weekday_mean")
    recent_weeks = serializers.IntegerField(required=False, min_value=1, max_value=12, default=4)
    moving_window_days = serializers.IntegerField(required=False, min_value=1, max_value=90, default=14)

    def validate_method(self, value):
        if value not in FORECAST_METHODS:
            allowed = ", ".join(FORECAST_METHODS.keys())
            raise serializers.ValidationError(
                f"Неизвестный метод прогнозирования: {value}. Доступно: {allowed}"
            )
        return value

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "date_to не может быть раньше date_from"}
            )
        return attrs


class ForecastCompareQuerySerializer(serializers.Serializer):
    methods = serializers.CharField(required=False, allow_blank=True)
    evaluation_start_date = serializers.DateField(required=False, allow_null=True)
    evaluation_end_date = serializers.DateField(required=False, allow_null=True)
    evaluation_days = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=90,
        default=DEFAULT_EVALUATION_DAYS,
    )
    recent_weeks = serializers.IntegerField(required=False, min_value=1, max_value=12, default=4)
    moving_window_days = serializers.IntegerField(required=False, min_value=1, max_value=90, default=14)
    min_train_days = serializers.IntegerField(required=False, min_value=7, max_value=365, default=21)

    def validate_methods(self, value):
        if not value:
            return []

        methods = [item.strip() for item in value.split(",") if item.strip()]
        invalid = [item for item in methods if item not in FORECAST_COMPARE_METHODS]
        if invalid:
            allowed = ", ".join(FORECAST_COMPARE_METHODS)
            raise serializers.ValidationError(
                f"Неизвестные методы: {', '.join(invalid)}. Доступно: {allowed}"
            )

        return list(dict.fromkeys(methods))

    def validate(self, attrs):
        evaluation_start_date = attrs.get("evaluation_start_date")
        evaluation_end_date = attrs.get("evaluation_end_date")

        if bool(evaluation_start_date) != bool(evaluation_end_date):
            raise serializers.ValidationError(
                {
                    "evaluation_start_date": (
                        "evaluation_start_date и evaluation_end_date нужно передавать вместе"
                    )
                }
            )

        if (
            evaluation_start_date
            and evaluation_end_date
            and evaluation_start_date > evaluation_end_date
        ):
            raise serializers.ValidationError(
                {"evaluation_end_date": "evaluation_end_date не может быть раньше evaluation_start_date"}
            )

        return attrs



class ForecastModalitySerializer(serializers.Serializer):
    modality = serializers.CharField()
    expected_studies = serializers.FloatField()
    expected_up = serializers.FloatField()
    recommended_doctors = serializers.IntegerField()


class ForecastChartPointSerializer(serializers.Serializer):
    date = serializers.CharField()
    label = serializers.CharField()
    expected_studies_total = serializers.FloatField()
    expected_up_total = serializers.FloatField(required=False)
    min_doctors = serializers.IntegerField()


class ForecastDaySerializer(serializers.Serializer):
    date = serializers.CharField()
    label = serializers.CharField()
    weekday = serializers.CharField()
    scheduled_doctors = serializers.IntegerField()
    expected_studies_total = serializers.FloatField()
    expected_up_total = serializers.FloatField()
    min_doctors = serializers.IntegerField()
    gap_to_schedule = serializers.IntegerField()
    required_modalities = ForecastModalitySerializer(many=True)


class ShiftForecastSummarySerializer(serializers.Serializer):
    total_expected_studies = serializers.FloatField()
    total_expected_up = serializers.FloatField()
    max_min_doctors_per_shift = serializers.IntegerField()
    modalities = serializers.ListField(child=serializers.CharField())


class ShiftForecastResponseSerializer(serializers.Serializer):
    date_from = serializers.CharField()
    date_to = serializers.CharField()
    history_start_date = serializers.CharField(allow_null=True)
    history_end_date = serializers.CharField(allow_null=True)
    generated_at = serializers.CharField()
    method = serializers.CharField(required=False)
    method_label = serializers.CharField(required=False)
    summary = ShiftForecastSummarySerializer()
    chart = ForecastChartPointSerializer(many=True)
    days = ForecastDaySerializer(many=True)
    message = serializers.CharField()
