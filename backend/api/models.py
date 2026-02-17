from django.db import models


class Doctor(models.Model):
    id = models.IntegerField(primary_key=True)
    fio_alias = models.CharField(max_length=255, blank=True, null=True)
    position_type = models.CharField(max_length=50, blank=True, null=True)
    max_up_per_day = models.IntegerField(default=120, blank=True, null=True)
    is_active = models.BooleanField(default=True, blank=True, null=True)
    
    class Meta:
        db_table = 'doctors'
        managed = False
    
    def __str__(self):
        return self.fio_alias or f"Doctor {self.id}"


class StudyType(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=500, blank=True, null=True)
    modality = models.CharField(max_length=50, blank=True, null=True)
    up_value = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    class Meta:
        db_table = 'study_types'
        managed = False
    
    def __str__(self):
        return f"{self.id} - {self.name}" if self.name else f"StudyType {self.id}"


class Schedule(models.Model):
    id = models.IntegerField(primary_key=True)
    doctor = models.ForeignKey(
        Doctor, 
        on_delete=models.CASCADE, 
        db_column='doctor_id',
        blank=True, 
        null=True
    )
    work_date = models.DateField(blank=True, null=True)
    time_start = models.TimeField(blank=True, null=True)
    time_end = models.TimeField(blank=True, null=True)
    is_day_off = models.IntegerField(default=0, blank=True, null=True)
    planned_up = models.IntegerField(blank=True, null=True)
    
    class Meta:
        db_table = 'schedules'
        managed = False
        ordering = ['work_date', 'time_start']
    
    def __str__(self):
        return f"Schedule {self.id} - {self.work_date}"


class Study(models.Model):
    id = models.IntegerField(primary_key=True)
    research_number = models.CharField(max_length=50, unique=True)
    study_type = models.ForeignKey(
        StudyType, 
        on_delete=models.CASCADE, 
        db_column='study_type_id', 
        blank=True, 
        null=True
    )
    status = models.CharField(max_length=50, blank=True, null=True)
    priority = models.CharField(max_length=20, default='normal', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    planned_at = models.DateTimeField(blank=True, null=True)
    diagnostician = models.ForeignKey(
        Doctor, 
        on_delete=models.CASCADE, 
        db_column='diagnostician_id', 
        blank=True, 
        null=True, 
        related_name='studies'
    )
    
    class Meta:
        db_table = 'studies'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        return self.research_number