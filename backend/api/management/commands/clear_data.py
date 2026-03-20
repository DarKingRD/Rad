from django.core.management.base import BaseCommand
from api.models import Doctor, Schedule, Study, StudyType

class Command(BaseCommand):
    help = 'Очистка данных таблиц'

    def handle(self, *args, **options):
        self.stdout.write('Начало очистки...')
        Study.objects.all().delete()
        Schedule.objects.all().delete()
        Doctor.objects.all().delete()
        StudyType.objects.all().delete()
        self.stdout.write('Очистка завершена.')