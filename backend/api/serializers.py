from datetime import datetime, date as d

from rest_framework import serializers

from .models import Doctor, StudyType, Schedule, Study
from .services.doctor_queries import (
    MONTHLY_NORM,
    format_time_hhmm,
    get_break_duration_minutes,
    get_daily_limit,
    get_doctor_specialty,
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
        data["modality"] = instance.modality or []
        return data


class StudyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyType
        fields = ["id", "name", "modality", "up_value"]


class ScheduleSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.fio_alias", read_only=True)
    break_duration_minutes = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "doctor",
            "doctor_name",
            "work_date",
            "time_start",
            "time_end",
            "break_start",
            "break_end",
            "break_duration_minutes",
            "is_day_off",
            "planned_up",
        ]
        read_only_fields = ["id", "doctor_name", "break_duration_minutes"]

    def get_break_duration_minutes(self, obj) -> int:
        return get_break_duration_minutes(obj)

    def validate_planned_up(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Планируемое количество УП не может быть отрицательным"
            )
        return value

    def validate(self, attrs):
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
        return attrs


class ScheduleWithDoctorSerializer(serializers.ModelSerializer):
    doctor = DoctorSerializer(read_only=True)
    break_duration_minutes = serializers.SerializerMethodField(read_only=True)

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
            "planned_up",
        ]

    def get_break_duration_minutes(self, obj) -> int:
        return get_break_duration_minutes(obj)


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
