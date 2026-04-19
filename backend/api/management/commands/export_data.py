from pathlib import Path
import csv
import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder


EXCLUDED_APPS_BY_DEFAULT = {"admin", "auth", "contenttypes", "sessions"}


class Command(BaseCommand):
    help = "Выгрузка данных из БД через Django ORM в JSON / JSONL / CSV"

    def add_arguments(self, parser):
        parser.add_argument(
            "--models",
            nargs="*",
            help="Список моделей в формате app_label.ModelName. "
                 "Пример: studies.Study doctors.Doctor",
        )
        parser.add_argument(
            "--format",
            choices=["json", "jsonl", "csv"],
            default="json",
            help="Формат выгрузки",
        )
        parser.add_argument(
            "--output",
            default="exports",
            help="Папка для сохранения файлов",
        )
        parser.add_argument(
            "--include-system",
            action="store_true",
            help="Включить системные Django-модели (auth, sessions и т.д.)",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output"])
        output_dir.mkdir(parents=True, exist_ok=True)

        export_format = options["format"]
        include_system = options["include_system"]

        models = self._get_models(options["models"], include_system)

        if not models:
            raise CommandError("Не найдено ни одной модели для выгрузки.")

        self.stdout.write(self.style.NOTICE(
            f"Найдено моделей для выгрузки: {len(models)}"
        ))

        for model in models:
            self._export_model(model, export_format, output_dir)

        self.stdout.write(self.style.SUCCESS(
            f"Готово. Данные сохранены в: {output_dir.resolve()}"
        ))

    def _get_models(self, model_labels, include_system):
        if model_labels:
            result = []
            for label in model_labels:
                model = apps.get_model(label)
                if model is None:
                    raise CommandError(
                        f"Модель '{label}' не найдена. "
                        f"Используй формат app_label.ModelName"
                    )
                result.append(model)
            return result

        result = []
        for model in apps.get_models():
            if not include_system and model._meta.app_label in EXCLUDED_APPS_BY_DEFAULT:
                continue
            result.append(model)

        return result

    def _serialize_instance(self, obj):
        data = {}

        # Обычные поля + ForeignKey как *_id
        for field in obj._meta.concrete_fields:
            key = field.attname  # для FK будет doctor_id, study_id и т.п.
            data[key] = getattr(obj, field.attname)

        # M2M поля как список id
        for m2m_field in obj._meta.many_to_many:
            data[m2m_field.name] = list(
                getattr(obj, m2m_field.name).values_list("pk", flat=True)
            )

        return data

    def _export_model(self, model, export_format, output_dir: Path):
        app_label = model._meta.app_label
        model_name = model.__name__
        file_name = f"{app_label}_{model_name.lower()}.{export_format}"
        file_path = output_dir / file_name

        queryset = model.objects.all()

        m2m_names = [field.name for field in model._meta.many_to_many]
        if m2m_names:
            queryset = queryset.prefetch_related(*m2m_names)

        count = queryset.count()

        if export_format == "csv":
            self._export_csv(model, queryset, file_path)
        elif export_format == "json":
            self._export_json(queryset, file_path)
        elif export_format == "jsonl":
            self._export_jsonl(queryset, file_path)
        else:
            raise CommandError(f"Неподдерживаемый формат: {export_format}")

        self.stdout.write(
            self.style.SUCCESS(
                f"{app_label}.{model_name}: {count} записей -> {file_path}"
            )
        )

    def _export_csv(self, model, queryset, file_path: Path):
        field_names = [field.attname for field in model._meta.concrete_fields]

        with file_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()

            for row in queryset.values(*field_names).iterator(chunk_size=2000):
                writer.writerow(row)

    def _export_json(self, queryset, file_path: Path):
        data = []
        for obj in queryset.iterator(chunk_size=2000):
            data.append(self._serialize_instance(obj))

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder)

    def _export_jsonl(self, queryset, file_path: Path):
        with file_path.open("w", encoding="utf-8") as f:
            for obj in queryset.iterator(chunk_size=2000):
                row = self._serialize_instance(obj)
                f.write(json.dumps(row, ensure_ascii=False, cls=DjangoJSONEncoder))
                f.write("\n")
