from rest_framework import serializers
from .models import Doctor, StudyType, Schedule, Study


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
        if value < 0:
            raise serializers.ValidationError("Максимальное количество УП не может быть отрицательным")
        return value

    def validate_fio_alias(self, value):
        if value and len(value.strip()) < 2:
            raise serializers.ValidationError("ФИО должно содержать минимум 2 символа")
        return value.strip() if value else None
    
    def get_specialty(self, obj):
        if obj.position_type == "radiologist":
            return "Рентгенолог"
        elif obj.position_type == "diagnostician":
            return "КТ-диагност"
        return obj.position_type or ""


class DoctorWithLoadSerializer(DoctorSerializer):
    current_load = serializers.IntegerField(default=0)
    max_load = serializers.IntegerField(default=50)
    active_studies = serializers.IntegerField(default=0)

    class Meta(DoctorSerializer.Meta):
        fields = DoctorSerializer.Meta.fields + [
            "current_load",
            "max_load",
            "active_studies",
        ]


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
        """Длительность перерыва в минутах — для удобства фронтенда."""
        if obj.break_start and obj.break_end:
            from datetime import datetime, date as d
            bs = datetime.combine(d.today(), obj.break_start)
            be = datetime.combine(d.today(), obj.break_end)
            delta = (be - bs).total_seconds()
            return int(delta // 60) if delta > 0 else 0
        return 0

    def validate_planned_up(self, value):
        if value < 0:
            raise serializers.ValidationError("Планируемое количество УП не может быть отрицательным")
        return value

    def validate(self, attrs):
        time_start  = attrs.get('time_start')
        time_end    = attrs.get('time_end')
        break_start = attrs.get('break_start')
        break_end   = attrs.get('break_end')

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
        if obj.break_start and obj.break_end:
            from datetime import datetime, date as d
            bs = datetime.combine(d.today(), obj.break_start)
            be = datetime.combine(d.today(), obj.break_end)
            delta = (be - bs).total_seconds()
            return int(delta // 60) if delta > 0 else 0
        return 0


class StudySerializer(serializers.ModelSerializer):
    class Meta:
        model = Study
        fields = "__all__"

    def validate_priority(self, value):
        if value not in ['normal', 'cito', 'asap']:
            raise serializers.ValidationError("Недопустимое значение приоритета")
        return value


class StudyWithDetailsSerializer(serializers.ModelSerializer):
    study_type = StudyTypeSerializer(read_only=True)
    diagnostician = DoctorSerializer(read_only=True)

    class Meta:
        model = Study
        fields = "__all__"


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
