from datetime import date, datetime
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from .serializers import DistributionRunSerializer
from .views import (
    chart_data,
    confirm_distribution,
    dashboard_stats,
    distribute_studies_view,
    distribution_preview,
)


class DistributionRunSerializerTests(SimpleTestCase):
    def test_validate_rejects_inverted_date_range(self):
        serializer = DistributionRunSerializer(
            data={"date_from": "2026-03-20", "date_to": "2026-03-19"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("date_to", serializer.errors)

    def test_validate_accepts_valid_date_range(self):
        serializer = DistributionRunSerializer(
            data={"date_from": "2026-03-19", "date_to": "2026-03-20"}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


class DashboardAndChartViewsTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("api.views.parse_dashboard_range", side_effect=ValueError)
    def test_dashboard_stats_returns_400_for_invalid_date_format(self, _parse_mock):
        request = self.factory.get(
            "/api/dashboard/stats/", {"date_from": "bad", "date_to": "date"}
        )

        response = dashboard_stats(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data,
            {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
        )

    @patch("api.views.get_chart_data")
    @patch("api.views.parse_dashboard_range")
    def test_chart_data_adjusts_exclusive_end_date_when_range_passed(
        self, parse_range_mock, get_chart_data_mock
    ):
        parse_range_mock.return_value = (
            datetime(2026, 3, 1, 0, 0),
            datetime(2026, 3, 11, 0, 0),
        )
        get_chart_data_mock.return_value = [{"name": "МРТ", "plan": 10, "actual": 8}]

        request = self.factory.get(
            "/api/dashboard/chart/",
            {"date_from": "2026-03-01", "date_to": "2026-03-10"},
        )

        response = chart_data(request)

        self.assertEqual(response.status_code, 200)
        get_chart_data_mock.assert_called_once_with(date(2026, 3, 1), date(2026, 3, 10))
        self.assertEqual(response.data, [{"name": "МРТ", "plan": 10, "actual": 8}])

    @patch("api.views.parse_dashboard_range")
    def test_chart_data_returns_400_when_start_after_end(self, parse_range_mock):
        parse_range_mock.return_value = (
            datetime(2026, 3, 15, 0, 0),
            datetime(2026, 3, 11, 0, 0),
        )
        request = self.factory.get("/api/dashboard/chart/")

        response = chart_data(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": "date_from не может быть позже date_to"})


class DistributionViewsTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("api.views.run_distribution")
    @patch("api.views.parse_distribution_datetime_end")
    @patch("api.views.parse_distribution_datetime_start")
    def test_distribute_post_uses_parsed_range_and_returns_service_result(
        self,
        parse_start_mock,
        parse_end_mock,
        run_distribution_mock,
    ):
        parse_start_mock.return_value = datetime(2026, 3, 1, 0, 0)
        parse_end_mock.return_value = datetime(2026, 3, 31, 23, 59)
        run_distribution_mock.return_value = {"distribution_id": "dist-1", "preview": True}

        request = self.factory.post(
            "/api/distribute/",
            {
                "date": "2026-03-15",
                "preview": True,
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
                "use_mip": False,
            },
            format="json",
        )

        response = distribute_studies_view(request)

        self.assertEqual(response.status_code, 200)
        parse_start_mock.assert_called_once_with("2026-03-01")
        parse_end_mock.assert_called_once_with("2026-03-31")
        run_distribution_mock.assert_called_once_with(
            target_date=date(2026, 3, 15),
            preview=True,
            date_from=datetime(2026, 3, 1, 0, 0),
            date_to=datetime(2026, 3, 31, 23, 59),
            use_mip=False,
        )
        self.assertEqual(response.data["distribution_id"], "dist-1")

    @patch("api.views.confirm_distribution_result", return_value=None)
    def test_confirm_distribution_returns_404_when_result_missing(self, _confirm_mock):
        request = self.factory.post(
            "/api/distribute/confirm/",
            {"distribution_id": "missing-id"},
            format="json",
        )

        response = confirm_distribution(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.data,
            {"error": "Распределение не найдено или истекло время (1 час)"},
        )

    @patch("api.views.get_distribution_preview_info")
    @patch("api.views.timezone.now")
    def test_distribution_preview_uses_today_when_date_not_passed(
        self, now_mock, preview_info_mock
    ):
        now_mock.return_value = timezone.make_aware(datetime(2026, 3, 23, 10, 0))
        preview_info_mock.return_value = {
            "pending_studies": 5,
            "available_doctors": 2,
            "target_date": "2026-03-23",
            "message": "ok",
        }

        request = self.factory.get("/api/distribute/preview/")

        response = distribution_preview(request)

        self.assertEqual(response.status_code, 200)
        preview_info_mock.assert_called_once_with(date(2026, 3, 23))
        self.assertEqual(response.data["target_date"], "2026-03-23")

    def test_distribution_preview_returns_400_for_invalid_date(self):
        request = self.factory.get("/api/distribute/preview/", {"date": "23-03-2026"})

        response = distribution_preview(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data,
            {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
        )
