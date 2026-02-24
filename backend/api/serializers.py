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

    def get_specialty(self, obj):
        if obj.position_type == "radiologist":
            return "Рентгенолог"
        elif obj.position_type == "diagnostician":
            return "КТ-диагност"
        return obj.position_type or ""


class DoctorWithLoadSerializer(DoctorSerializer):
    current_load = serializers.IntegerField(default=0)
    max_load = serializers.IntegerField(default=120)
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

    class Meta:
        model = Schedule
        fields = [
            "id",
            "doctor",
            "doctor_name",
            "work_date",
            "time_start",
            "time_end",
            "is_day_off",
            "planned_up",
        ]
        read_only_fields = ["id", "doctor_name"]


class ScheduleWithDoctorSerializer(serializers.ModelSerializer):
    doctor = DoctorSerializer(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "doctor",
            "work_date",
            "time_start",
            "time_end",
            "is_day_off",
            "planned_up",
        ]


class StudySerializer(serializers.ModelSerializer):
    class Meta:
        model = Study
        fields = "__all__"


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
