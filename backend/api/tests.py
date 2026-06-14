from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from django.contrib.auth.models import AnonymousUser, User
from rest_framework.test import APIRequestFactory, force_authenticate

from .serializers import DistributionRunSerializer
from .services.distribution.entities import DoctorData, StudyData
from .services.distribution.exact_solver import build_exact_options
from .services.distribution.objectives import WeightedTardinessLexicographicObjective
from .services.distribution.result_builder import build_distribution_response
from .services.distribution_api import parse_distribution_datetime_end
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

    def test_validate_accepts_objective(self):
        serializer = DistributionRunSerializer(
            data={"objective": "priority_tier_tardiness_multipass"}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["objective"],
            "priority_tier_tardiness_multipass",
        )

    def test_distribution_end_date_is_inclusive(self):
        self.assertEqual(
            parse_distribution_datetime_end("2026-03-20"),
            datetime(2026, 3, 21, 0, 0),
        )


class ForecastCompareQuerySerializerTests(SimpleTestCase):
    def test_validate_accepts_evaluation_date_range(self):
        from .serializers import ForecastCompareQuerySerializer

        serializer = ForecastCompareQuerySerializer(
            data={
                "evaluation_start_date": "2025-10-13",
                "evaluation_end_date": "2025-10-19",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["evaluation_start_date"],
            date(2025, 10, 13),
        )
        self.assertEqual(
            serializer.validated_data["evaluation_end_date"],
            date(2025, 10, 19),
        )

    def test_validate_rejects_single_evaluation_date(self):
        from .serializers import ForecastCompareQuerySerializer

        serializer = ForecastCompareQuerySerializer(
            data={"evaluation_start_date": "2025-10-13"}
        )

        self.assertFalse(serializer.is_valid())

    def test_validate_accepts_default_forecast_methods(self):
        from .serializers import ForecastCompareQuerySerializer

        serializer = ForecastCompareQuerySerializer(
            data={
                "methods": (
                    "weekday_mean,linear_regression,"
                    "poisson_regression,holt_winters"
                )
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["methods"],
            [
                "weekday_mean",
                "linear_regression",
                "poisson_regression",
                "holt_winters",
            ],
        )

    def test_validate_rejects_split_methods(self):
        from .serializers import ForecastCompareQuerySerializer

        serializer = ForecastCompareQuerySerializer(
            data={"methods": "linear_regression_split"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("methods", serializer.errors)


class ForecastCompareMethodsTests(SimpleTestCase):
    @patch("api.services.shift_forecast_multi_method._load_actual_day_totals")
    @patch("api.services.shift_forecast_multi_method.build_shift_forecast")
    @patch("api.services.shift_forecast_multi_method._get_history_bounds")
    def test_default_comparison_holds_out_last_week_from_training(
        self,
        history_bounds_mock,
        build_forecast_mock,
        actual_totals_mock,
    ):
        from .services.shift_forecast_multi_method import evaluate_forecast_methods

        history_bounds_mock.return_value = (date(2025, 10, 1), date(2025, 10, 31))
        actual_totals_mock.return_value = {
            date(2025, 10, day): {"studies_count": 10.0, "total_up": 15.0}
            for day in range(25, 32)
        }
        build_forecast_mock.return_value = {
            "days": [
                {
                    "date": date(2025, 10, day).isoformat(),
                    "expected_studies_total": 10.0,
                    "expected_up_total": 15.0,
                }
                for day in range(25, 32)
            ]
        }

        result = evaluate_forecast_methods(
            methods=["weekday_mean"],
            evaluation_days=7,
            min_train_days=1,
        )

        self.assertEqual(result["evaluation_start_date"], "2025-10-25")
        self.assertEqual(result["evaluation_end_date"], "2025-10-31")
        self.assertEqual(result["training_start_date"], "2025-10-01")
        self.assertEqual(result["training_end_date"], "2025-10-24")
        self.assertEqual(result["comparison_mode"], "holdout_last_period")
        build_forecast_mock.assert_called_once()
        self.assertEqual(
            build_forecast_mock.call_args.kwargs["history_start_override"],
            date(2025, 10, 1),
        )
        self.assertEqual(
            build_forecast_mock.call_args.kwargs["history_end_override"],
            date(2025, 10, 24),
        )

    @patch("api.services.shift_forecast_multi_method._forecast_with_linear_regression")
    def test_linear_regression_derives_up_from_predicted_studies(self, forecast_mock):
        from .services.shift_forecast_multi_method import _forecast_model_based_totals

        history_start = date(2025, 10, 6)
        history_end = date(2025, 10, 12)
        history_days = [history_start + timedelta(days=offset) for offset in range(7)]
        totals_map = {
            current_day: {
                "studies_count": 10.0,
                "total_up": 10.0 * (current_day.weekday() + 2),
            }
            for current_day in history_days
        }
        monday = date(2025, 10, 13)
        tuesday = date(2025, 10, 14)
        forecast_mock.return_value = {
            monday: 100.0,
            tuesday: 200.0,
        }

        result = _forecast_model_based_totals(
            forecast_days=[monday, tuesday],
            history_start=history_start,
            history_end=history_end,
            totals_map=totals_map,
            method="linear_regression",
        )

        self.assertEqual(forecast_mock.call_count, 1)
        self.assertEqual(forecast_mock.call_args.kwargs["target_key"], "studies_count")
        self.assertEqual(result[monday]["studies_count"], 100.0)
        self.assertEqual(result[monday]["total_up"], 200.0)
        self.assertEqual(result[tuesday]["studies_count"], 200.0)
        self.assertEqual(result[tuesday]["total_up"], 600.0)

    def test_outlier_smoothing_uses_same_weekday_peers(self):
        from .services.shift_forecast_multi_method import _smooth_daily_totals

        mondays = [date(2025, 10, 6) + timedelta(days=7 * offset) for offset in range(5)]
        saturdays = [date(2025, 10, 4) + timedelta(days=7 * offset) for offset in range(5)]
        monday_values = [100.0, 102.0, 98.0, 101.0, 5.0]
        saturday_values = [10.0, 11.0, 9.0, 12.0, 100.0]
        totals_map = {
            current_day: {
                "studies_count": value,
                "total_up": value * 2,
            }
            for current_day, value in zip(mondays + saturdays, monday_values + saturday_values)
        }

        smoothed = _smooth_daily_totals(
            totals_map=totals_map,
            history_days=mondays + saturdays,
        )

        self.assertEqual(smoothed[mondays[0]]["studies_count"], 100.0)
        self.assertGreater(smoothed[mondays[-1]]["studies_count"], 90.0)
        self.assertLess(smoothed[saturdays[-1]]["studies_count"], 20.0)
        self.assertGreater(smoothed[mondays[-1]]["total_up"], 180.0)
        self.assertLess(smoothed[saturdays[-1]]["total_up"], 40.0)

    def test_outlier_smoothing_ignores_empty_calendar_days(self):
        from .services.shift_forecast_multi_method import _smooth_daily_totals

        mondays = [date(2025, 10, 6) + timedelta(days=7 * offset) for offset in range(8)]
        totals_map = {
            current_day: {"studies_count": 0.0, "total_up": 0.0}
            for current_day in mondays
        }
        totals_map[mondays[1]] = {"studies_count": 12.0, "total_up": 24.0}
        totals_map[mondays[5]] = {"studies_count": 18.0, "total_up": 36.0}

        smoothed = _smooth_daily_totals(
            totals_map=totals_map,
            history_days=mondays,
        )

        self.assertEqual(smoothed[mondays[1]]["studies_count"], 12.0)
        self.assertEqual(smoothed[mondays[5]]["studies_count"], 18.0)
        self.assertEqual(smoothed[mondays[1]]["total_up"], 24.0)
        self.assertEqual(smoothed[mondays[5]]["total_up"], 36.0)

    def test_weekday_mean_ignores_empty_history_days(self):
        from .services.shift_forecast_multi_method import FORECAST_XRAY, _build_profile_for_day

        first_monday = date(2025, 10, 6)
        empty_monday = date(2025, 10, 13)
        second_monday = date(2025, 10, 20)
        forecast_monday = date(2025, 10, 27)
        daily_series = {
            first_monday: {
                FORECAST_XRAY: {"studies_count": 10.0, "total_up": 20.0},
            },
            empty_monday: {},
            second_monday: {
                FORECAST_XRAY: {"studies_count": 20.0, "total_up": 40.0},
            },
        }

        profile = _build_profile_for_day(
            target_day=forecast_monday,
            daily_series=daily_series,
            modalities=[FORECAST_XRAY],
            history_start=first_monday,
            history_end=second_monday,
            method="weekday_mean",
            recent_weeks=4,
            moving_window_days=14,
        )

        self.assertEqual(len(profile), 1)
        self.assertEqual(profile[0]["expected_studies"], 15.0)
        self.assertEqual(profile[0]["expected_up"], 30.0)


class DashboardAndChartViewsTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User(username="test_manager", is_staff=True)

    @patch("api.views.parse_dashboard_range", side_effect=ValueError)
    def test_dashboard_stats_returns_400_for_invalid_date_format(self, _parse_mock):
        request = self.factory.get(
            "/api/dashboard/stats/", {"date_from": "bad", "date_to": "date"}
        )
        force_authenticate(request, user=self.user) 

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
        
        force_authenticate(request, user=self.user)

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

        force_authenticate(request, user=self.user)
        
        response = chart_data(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": "date_from не может быть позже date_to"})


class DistributionResultBuilderTests(SimpleTestCase):
    def test_summary_reports_tardiness_reduction_from_assignments(self):
        base = timezone.make_aware(datetime(2026, 3, 20, 9, 0))
        doctor = DoctorData(
            id=1,
            name="Doctor",
            modality={"CT"},
            max_up=8.0,
            shift_start=base,
            shift_end=timezone.make_aware(datetime(2026, 3, 20, 18, 0)),
        )
        studies = [
            StudyData(
                research_number="s1",
                priority="normal",
                created_at=base,
                modality={"CT"},
                up_value=1.0,
                duration_minutes=30.0,
                deadline=timezone.make_aware(datetime(2026, 3, 20, 10, 0)),
                weight=1.0,
            ),
            StudyData(
                research_number="s2",
                priority="normal",
                created_at=base,
                modality={"CT"},
                up_value=1.0,
                duration_minutes=30.0,
                deadline=timezone.make_aware(datetime(2026, 3, 20, 11, 0)),
                weight=1.0,
            ),
        ]

        result = build_distribution_response(
            studies=studies,
            doctors=[doctor],
            assignment={"s1": 1},
            details={
                "s1": {
                    "doctor_id": 1,
                    "start_dt": base,
                    "finish_dt": timezone.make_aware(datetime(2026, 3, 20, 12, 0)),
                    "tardiness_hours": 2.0,
                    "weighted_tardiness": 2.0,
                    "objective_value": 2.0,
                }
            },
            unassigned_meta={
                "s2": {
                    "virtual_finish_dt": timezone.make_aware(datetime(2026, 3, 20, 16, 0)),
                    "tardiness_hours": 5.0,
                    "weighted_tardiness": 5.0,
                    "objective_value": 5.0,
                }
            },
            baseline_unassigned_meta={
                "s1": {
                    "virtual_finish_dt": timezone.make_aware(datetime(2026, 3, 20, 18, 0)),
                    "tardiness_hours": 8.0,
                    "weighted_tardiness": 8.0,
                    "objective_value": 8.0,
                },
                "s2": {
                    "virtual_finish_dt": timezone.make_aware(datetime(2026, 3, 20, 16, 0)),
                    "tardiness_hours": 5.0,
                    "weighted_tardiness": 5.0,
                    "objective_value": 5.0,
                },
            },
            solver_obj=7.0,
            now=base,
            preview_mode=True,
            target_date_iso="2026-03-20",
            objective_code="weighted_tardiness_lexicographic",
            objective_meta={},
            debug_log=[],
        )

        self.assertEqual(result["summary"]["baseline_total_tardiness"], 13.0)
        self.assertEqual(result["summary"]["total_tardiness"], 7.0)
        self.assertEqual(result["summary"]["tardiness_reduction"], 6.0)
        self.assertEqual(result["summary"]["tardiness_reduction_percent"], 46.15)
        self.assertEqual(result["summary"]["queue_overdue_hours_total"], 0.0)
        self.assertEqual(result["summary"]["queue_overdue_hours_assigned"], 0.0)
        self.assertEqual(result["summary"]["queue_overdue_hours_remaining"], 0.0)
        self.assertEqual(result["summary"]["scheduled_overdue_total"], 2)
        self.assertEqual(result["summary"]["scheduled_overdue_assigned"], 1)
        self.assertEqual(result["summary"]["scheduled_overdue_unassigned"], 1)
        self.assertEqual(result["summary"]["scheduled_overdue_hours_total"], 7.0)
        self.assertEqual(result["summary"]["scheduled_overdue_hours_assigned"], 2.0)
        self.assertEqual(result["summary"]["scheduled_overdue_hours_unassigned"], 5.0)
        self.assertEqual(result["priority_breakdown"]["plan"]["share_percent"], 100.0)
        self.assertEqual(result["priority_breakdown"]["plan"]["overdue_rate_percent"], 0.0)
        self.assertEqual(result["priority_breakdown"]["plan"]["scheduled_overdue_assigned"], 1)
        self.assertEqual(result["priority_breakdown"]["plan"]["scheduled_overdue_hours_assigned"], 2.0)
        self.assertEqual(result["priority_breakdown"]["plan"]["tardiness_reduction"], 6.0)
        assigned = next(item for item in result["assignments"] if item["study_number"] == "s1")
        self.assertEqual(assigned["tardiness_reduction"], 6.0)


class ExactSolverOptionBuilderTests(SimpleTestCase):
    def test_disabled_variant_cap_keeps_late_start_options(self):
        base = timezone.make_aware(datetime(2026, 3, 20, 9, 0))
        doctor = DoctorData(
            id=1,
            name="Doctor",
            modality={"CT"},
            max_up=8.0,
            shift_start=base,
            shift_end=timezone.make_aware(datetime(2026, 3, 20, 9, 30)),
        )
        study = StudyData(
            research_number="s1",
            priority="cito",
            created_at=base,
            modality={"CT"},
            up_value=1.0,
            duration_minutes=5.0,
            deadline=base,
            weight=64.0,
        )

        with patch("api.services.distribution.exact_solver.EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR", None):
            options, *_ = build_exact_options(
                studies=[study],
                doctors=[doctor],
                objective=WeightedTardinessLexicographicObjective(),
                priority_weights={"cito": 64.0, "asap": 8.0, "normal": 1.0},
                planning_now=base,
                log=lambda _message: None,
            )

        self.assertEqual(len(options), 6)
        self.assertEqual(options[-1].start_dt, timezone.make_aware(datetime(2026, 3, 20, 9, 25)))

class DistributionViewsTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User(username="test_manager", is_staff=True)

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
        parse_end_mock.return_value = datetime(2026, 4, 1, 0, 0)
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
        
        force_authenticate(request, user=self.user)

        response = distribute_studies_view(request)

        self.assertEqual(response.status_code, 200)
        parse_start_mock.assert_called_once_with("2026-03-01")
        parse_end_mock.assert_called_once_with("2026-03-31")
        run_distribution_mock.assert_called_once_with(
            target_date=date(2026, 3, 15),
            preview=True,
            date_from=datetime(2026, 3, 1, 0, 0),
            date_to=datetime(2026, 4, 1, 0, 0),
            use_mip=False,
            objective="weighted_tardiness_lexicographic",
        )
        self.assertEqual(response.data["distribution_id"], "dist-1")

    @patch("api.views.confirm_distribution_result", return_value=None)
    def test_confirm_distribution_returns_404_when_result_missing(self, _confirm_mock):
        request = self.factory.post(
            "/api/distribute/confirm/",
            {"distribution_id": "missing-id"},
            format="json",
        )
        
        force_authenticate(request, user=self.user)

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

        force_authenticate(request, user=self.user)
        
        response = distribution_preview(request)

        self.assertEqual(response.status_code, 200)
        preview_info_mock.assert_called_once_with(date(2026, 3, 23))
        self.assertEqual(response.data["target_date"], "2026-03-23")

    def test_distribution_preview_returns_400_for_invalid_date(self):
        request = self.factory.get("/api/distribute/preview/", {"date": "23-03-2026"})

        force_authenticate(request, user=self.user)
        
        response = distribution_preview(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data,
            {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
        )
