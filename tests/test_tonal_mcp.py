import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


class FakeFastMCP:
    def __init__(self, *args, **kwargs):
        pass

    def tool(self):
        return lambda function: function


fastmcp_module = types.ModuleType("mcp.server.fastmcp")
fastmcp_module.FastMCP = FakeFastMCP
sys.modules.setdefault("mcp", types.ModuleType("mcp"))
sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
sys.modules["mcp.server.fastmcp"] = fastmcp_module

module_path = Path(__file__).parents[1] / "mcp" / "tonal_mcp.py"
spec = importlib.util.spec_from_file_location("tonal_mcp", module_path)
tonal_mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tonal_mcp)

cli_path = Path(__file__).parents[1] / "tonal_tool.py"
cli_spec = importlib.util.spec_from_file_location("tonal_tool", cli_path)
tonal_tool = importlib.util.module_from_spec(cli_spec)
cli_spec.loader.exec_module(tonal_tool)


class WorkoutDetailTests(unittest.TestCase):
    def test_normalizes_straight_bar_load_and_includes_warmup_volume(self):
        activity = {
            "id": "activity-1",
            "totalDuration": 600,
            "totalVolume": 250,
            "workoutSetActivity": [
                {
                    "movementId": "straight-bar",
                    "repCount": 10,
                    "baseWeight": 24.5,
                    "volume": 50,
                    "oneRepMax": 34.8,
                    "suggestedWeight": 43.8,
                    "rom": 10.25,
                    "inconsistencyScore": 0.1,
                    "spotterMode": "SPOTTER",
                    "warmUp": True,
                },
                {
                    "movementId": "straight-bar",
                    "repCount": 6,
                    "baseWeight": 42,
                    "volume": 100,
                    "oneRepMax": 52.36,
                    "suggestedWeight": 49.39,
                    "rom": 22.345,
                    "inconsistencyScore": 0.2345,
                    "spotter": True,
                    "eccentric": True,
                    "chains": False,
                    "burnout": True,
                    "dropSet": False,
                    "duration": 31,
                    "warmUp": False,
                },
                {
                    "movementId": "handles",
                    "repCount": 6,
                    "baseWeight": 30,
                    "volume": 60,
                    "oneRepMax": 38,
                    "suggestedWeight": 32,
                    "rom": 0,
                    "inconsistencyScore": -1,
                    "warmUp": False,
                },
                {
                    "movementId": "warmup-only",
                    "repCount": 4,
                    "baseWeight": 10,
                    "volume": 40,
                    "oneRepMax": 12,
                    "suggestedWeight": 11,
                    "warmUp": True,
                },
            ],
        }
        movement_map = {
            "straight-bar": {
                "name": "Barbell Bench Press",
                "isBilateral": True,
                "onMachineInfo": {"accessory": "StraightBar"},
            },
            "handles": {
                "name": "Bench Press",
                "isBilateral": True,
                "onMachineInfo": {"accessory": "Handles"},
            },
            "warmup-only": {
                "name": "Activation",
                "isBilateral": False,
                "onMachineInfo": {"accessory": "Handles"},
            },
        }

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activity),
            patch.object(tonal_mcp, "_movement_map", return_value=movement_map),
        ):
            result = tonal_mcp.get_workout_detail("activity-1")

        by_id = {movement["movement_id"]: movement for movement in result["movements"]}
        straight_bar = by_id["straight-bar"]
        handles = by_id["handles"]
        warmup_only = by_id["warmup-only"]
        self.assertEqual(straight_bar["set_details"][0]["weight_lbs"], 84)
        self.assertEqual(straight_bar["set_details"][0]["one_rep_max"], 105)
        self.assertEqual(straight_bar["set_details"][0]["suggested_weight"], 98.8)
        self.assertEqual(straight_bar["set_details"][0]["rom_inches"], 22.3)
        self.assertEqual(straight_bar["set_details"][0]["inconsistency_score"], 0.23)
        self.assertTrue(straight_bar["set_details"][0]["spotter"])
        self.assertTrue(straight_bar["set_details"][0]["eccentric"])
        self.assertFalse(straight_bar["set_details"][0]["chains"])
        self.assertTrue(straight_bar["set_details"][0]["burnout"])
        self.assertFalse(straight_bar["set_details"][0]["drop_set"])
        self.assertEqual(straight_bar["set_details"][0]["duration_sec"], 31)
        self.assertEqual(straight_bar["warmup_set_details"][0]["rom_inches"], 10.2)
        self.assertEqual(
            straight_bar["warmup_set_details"][0]["inconsistency_score"], 0.1
        )
        self.assertTrue(straight_bar["warmup_set_details"][0]["spotter"])
        self.assertEqual(straight_bar["working_volume_lbs"], 100)
        self.assertEqual(straight_bar["warmup_volume_lbs"], 50)
        self.assertEqual(straight_bar["total_volume_lbs"], 150)

        self.assertEqual(handles["set_details"][0]["weight_lbs"], 30)
        self.assertEqual(handles["set_details"][0]["one_rep_max"], 38)
        self.assertIsNone(handles["set_details"][0]["rom_inches"])
        self.assertIsNone(handles["set_details"][0]["inconsistency_score"])
        self.assertEqual(handles["total_volume_lbs"], 60)

        self.assertEqual(warmup_only["working_sets"], 0)
        self.assertEqual(warmup_only["warmup_sets"], 1)
        self.assertEqual(warmup_only["working_volume_lbs"], 0)
        self.assertEqual(warmup_only["warmup_volume_lbs"], 40)
        self.assertEqual(warmup_only["total_volume_lbs"], 40)
        self.assertEqual(warmup_only["set_details"], [])

        self.assertEqual(result["total_volume_lbs"], 250)
        self.assertEqual(
            sum(movement["total_volume_lbs"] for movement in result["movements"]),
            result["total_volume_lbs"],
        )

    def test_load_multiplier_requires_bilateral_straight_bar(self):
        self.assertEqual(
            tonal_mcp._load_multiplier(
                {"isBilateral": True, "onMachineInfo": {"accessory": "StraightBar"}}
            ),
            2,
        )
        self.assertEqual(
            tonal_mcp._load_multiplier(
                {"isBilateral": False, "onMachineInfo": {"accessory": "StraightBar"}}
            ),
            1,
        )
        self.assertEqual(
            tonal_mcp._load_multiplier(
                {"isBilateral": True, "onMachineInfo": {"accessory": "Handles"}}
            ),
            1,
        )

    def test_cli_detail_exposes_same_performance_fields(self):
        activity = {
            "id": "activity-1",
            "workoutSetActivity": [
                {
                    "movementId": "movement-1",
                    "repCount": 5,
                    "baseWeight": 20,
                    "volume": 100,
                    "rom": 12.345,
                    "inconsistencyScore": 0.4567,
                    "spotter": True,
                    "eccentric": True,
                    "chains": True,
                    "burnout": False,
                    "dropSet": True,
                    "duration": 25,
                },
                {
                    "movementId": "movement-1",
                    "repCount": 2,
                    "baseWeight": 10,
                    "volume": 20,
                    "rom": None,
                    "inconsistencyScore": None,
                    "spotterMode": "SPOTTER",
                    "warmUp": True,
                }
            ],
        }
        with (
            patch.object(tonal_tool, "get_user_id", return_value="user-1"),
            patch.object(tonal_tool, "api_get", return_value=activity),
            patch.object(
                tonal_tool,
                "_get_movement_map",
                return_value={"movement-1": {"name": "Bench Press"}},
            ),
        ):
            result = tonal_tool.cmd_detail(["activity-1"])

        set_detail = result["movements"][0]["set_details"][0]
        self.assertEqual(set_detail["rom_inches"], 12.3)
        self.assertEqual(set_detail["inconsistency_score"], 0.46)
        self.assertTrue(set_detail["spotter"])
        self.assertTrue(set_detail["eccentric"])
        self.assertTrue(set_detail["chains"])
        self.assertFalse(set_detail["burnout"])
        self.assertTrue(set_detail["drop_set"])
        self.assertEqual(set_detail["duration_sec"], 25)
        self.assertEqual(result["movements"][0]["working_volume_lbs"], 100)
        self.assertEqual(result["movements"][0]["warmup_volume_lbs"], 20)
        self.assertEqual(result["movements"][0]["total_volume_lbs"], 120)
        warmup_detail = result["movements"][0]["warmup_set_details"][0]
        self.assertIsNone(warmup_detail["rom_inches"])
        self.assertIsNone(warmup_detail["inconsistency_score"])
        self.assertTrue(warmup_detail["spotter"])

    def test_performance_summary_preserves_left_right_splits(self):
        formatted = {
            "movementSets": [
                {
                    "movementName": "Single-Arm Press",
                    "sets": [
                        {
                            "repCount": 8,
                            "weight": 20,
                            "leftSideMovementSet": {"repCount": 8, "weight": 19},
                            "rightSideMovementSet": {
                                "repCount": 7,
                                "weight": 20,
                                "oneRepMax": 24,
                                "maxConPower": 100,
                                "totalVolume": 140,
                            },
                        }
                    ],
                }
            ]
        }
        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(
                tonal_mcp, "_strength_activity_data", return_value=formatted
            ),
        ):
            result = tonal_mcp.get_performance_summary("activity-1")

        set_detail = result["movements"][0]["sets"][0]
        self.assertEqual(set_detail["left"]["reps"], 8)
        self.assertEqual(set_detail["left"]["weight_lbs"], 19)
        self.assertEqual(
            set_detail["right"],
            {
                "reps": 7,
                "weight_lbs": 20,
                "one_rep_max": 24,
                "max_power_watts": 100,
                "volume_lbs": 140,
            },
        )


class ActivityTypeTests(unittest.TestCase):
    def setUp(self):
        self.internal = {
            "activityId": "internal-1",
            "activityTime": "2026-07-29T12:00:00Z",
            "activityType": "Internal",
            "workoutPreview": {
                "workoutTitle": "Strength",
                "totalDuration": 600,
                "totalVolume": 100,
                "targetArea": "FULL BODY",
            },
        }
        self.external = {
            "activityId": "external-1",
            "activityTime": "2026-07-28T12:00:00Z",
            "activityType": "External",
            "workoutPreview": {
                "workoutTitle": "",
                "totalDuration": 3600,
                "totalVolume": 0,
                "targetArea": "",
            },
        }

    def test_history_exposes_activity_type_and_filters_strength(self):
        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(
                tonal_mcp, "_api_get", return_value=[self.internal, self.external]
            ),
        ):
            all_history = tonal_mcp.get_workout_history()
            strength_history = tonal_mcp.get_workout_history(strength_only=True)

        self.assertEqual(
            [
                (workout["activity_type"], workout["has_strength_data"])
                for workout in all_history["workouts"]
            ],
            [("Internal", True), ("External", False)],
        )
        self.assertEqual(
            [workout["activity_id"] for workout in strength_history["workouts"]],
            ["internal-1"],
        )
        self.assertEqual(all_history["returned_count"], 2)
        self.assertEqual(strength_history["available_in_page"], 1)
        self.assertFalse(strength_history["requested_limit_satisfied"])
        self.assertTrue(strength_history["source_page_exhausted"])
        self.assertFalse(all_history["upstream_page_may_be_truncated"])

    def test_history_enforces_local_limit_and_reports_fixed_page(self):
        activities = [
            {
                **self.internal,
                "activityId": f"internal-{index}",
                "activityTime": f"2026-07-{29 - index:02d}T12:00:00Z",
            }
            for index in range(20)
        ] + [
            {
                **self.external,
                "activityId": f"external-{index}",
                "activityTime": f"2026-06-{30 - index:02d}T12:00:00Z",
            }
            for index in range(30)
        ]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            one = tonal_mcp.get_workout_history(limit=1)
            five = tonal_mcp.get_workout_history(limit=5)
            default = tonal_mcp.get_workout_history()
            fifty = tonal_mcp.get_workout_history(limit=50)
            strength = tonal_mcp.get_workout_history(limit=10, strength_only=True)

        self.assertEqual(len(one["workouts"]), 1)
        self.assertEqual(len(five["workouts"]), 5)
        self.assertEqual(len(default["workouts"]), 10)
        self.assertEqual(len(fifty["workouts"]), 50)
        self.assertEqual(len(strength["workouts"]), 10)
        self.assertEqual(strength["available_in_page"], 20)
        self.assertTrue(strength["more_available_in_page"])
        self.assertTrue(strength["requested_limit_satisfied"])
        self.assertFalse(strength["source_page_exhausted"])
        self.assertTrue(strength["upstream_page_may_be_truncated"])
        self.assertEqual(strength["source_count"], 50)

    def test_strength_limit_reports_incomplete_when_fixed_page_has_four_matches(self):
        activities = [
            {**self.internal, "activityId": f"internal-{index}"}
            for index in range(4)
        ] + [
            {**self.external, "activityId": f"external-{index}"}
            for index in range(46)
        ]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            history = tonal_mcp.get_workout_history(limit=10, strength_only=True)

        self.assertEqual(history["returned_count"], 4)
        self.assertEqual(history["available_in_page"], 4)
        self.assertFalse(history["requested_limit_satisfied"])
        self.assertFalse(history["source_page_exhausted"])
        self.assertTrue(history["upstream_page_may_be_truncated"])

    def test_strength_limit_distinguishes_short_page_from_satisfied_limit(self):
        activities = [
            {**self.internal, "activityId": f"internal-{index}"}
            for index in range(4)
        ] + [
            {**self.external, "activityId": f"external-{index}"}
            for index in range(45)
        ]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            history = tonal_mcp.get_workout_history(limit=10, strength_only=True)

        self.assertEqual(history["returned_count"], 4)
        self.assertFalse(history["requested_limit_satisfied"])
        self.assertTrue(history["source_page_exhausted"])

    def test_history_rejects_invalid_limits_without_api_call(self):
        with patch.object(tonal_mcp, "_api_get") as api_get:
            zero = tonal_mcp.get_workout_history(limit=0)
            too_large = tonal_mcp.get_workout_history(limit=51)

        self.assertEqual(zero["error"], "invalid_limit")
        self.assertEqual(too_large["error"], "invalid_limit")
        api_get.assert_not_called()

    def test_volume_report_counts_only_internal_activities(self):
        activity_time = datetime.now(timezone.utc).isoformat()
        internal = {**self.internal, "activityTime": activity_time}
        external = {**self.external, "activityTime": activity_time}

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=[internal, external]),
        ):
            report = tonal_mcp.get_volume_report(days=7)

        self.assertEqual(report["total_workouts"], 1)
        self.assertEqual(report["total_volume_lbs"], 100)
        self.assertEqual(report["avg_volume_per_session"], 100)
        self.assertEqual(report["unparseable_activity_count"], 0)
        self.assertTrue(report["is_complete"])

    def test_volume_report_marks_incomplete_fixed_page(self):
        activity_time = datetime.now(timezone.utc).isoformat()
        activities = [
            {
                **self.internal,
                "activityId": f"internal-{index}",
                "activityTime": activity_time,
            }
            for index in range(50)
        ]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            report = tonal_mcp.get_volume_report(days=365)

        self.assertEqual(report["source_count"], 50)
        self.assertFalse(report["is_complete"])

    def test_volume_report_marks_full_page_complete_when_cutoff_is_covered(self):
        activities = [
            {
                **self.internal,
                "activityId": f"internal-{index}",
                "activityTime": "2024-01-01T12:00:00Z",
            }
            for index in range(50)
        ]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            report = tonal_mcp.get_volume_report(days=365)

        self.assertEqual(report["source_count"], 50)
        self.assertTrue(report["is_complete"])

    def test_volume_report_returns_stable_empty_schema(self):
        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=[]),
        ):
            report = tonal_mcp.get_volume_report(days=30)

        self.assertEqual(report["days"], 30)
        self.assertEqual(report["period_days"], 30)
        self.assertEqual(report["workouts"], 0)
        self.assertEqual(report["total_workouts"], 0)
        self.assertEqual(report["workouts_per_week"], 0)
        self.assertEqual(report["total_volume_lbs"], 0)
        self.assertEqual(report["avg_volume_per_session"], 0)
        self.assertEqual(report["by_target_area"], {})
        self.assertEqual(report["by_week"], {})
        self.assertEqual(report["unparseable_activity_count"], 0)
        self.assertTrue(report["is_complete"])

    def test_volume_report_fails_completeness_closed_for_bad_timestamps(self):
        activities = [
            {
                **self.internal,
                "activityId": f"internal-{index}",
                "activityTime": "2024-01-01T12:00:00Z",
            }
            for index in range(49)
        ] + [{**self.internal, "activityId": "bad-time", "activityTime": 123}]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            report = tonal_mcp.get_volume_report(days=365)

        self.assertEqual(report["unparseable_activity_count"], 1)
        self.assertFalse(report["is_complete"])
        self.assertTrue(report["upstream_page_may_be_truncated"])

    def test_activity_datetime_accepts_common_iso_forms_and_rejects_bad_values(self):
        expected = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
        self.assertEqual(
            tonal_mcp._activity_datetime({"activityTime": "2026-07-29T12:00:00Z"}),
            expected,
        )
        self.assertEqual(
            tonal_mcp._activity_datetime(
                {"activityTime": "2026-07-29T08:00:00-04:00"}
            ),
            expected,
        )
        self.assertEqual(
            tonal_mcp._activity_datetime({"activityTime": "2026-07-29T12:00:00"}),
            expected,
        )
        for value in (None, 123, {}, "not-a-date"):
            self.assertIsNone(tonal_mcp._activity_datetime({"activityTime": value}))

    def test_exercise_history_marks_fixed_page_as_possibly_truncated(self):
        activities = [
            {**self.external, "activityId": f"external-{index}"}
            for index in range(50)
        ]

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(
                tonal_mcp,
                "_movement_map",
                return_value={"movement-1": {"name": "Bench Press"}},
            ),
            patch.object(tonal_mcp, "_api_get", return_value=activities),
        ):
            history = tonal_mcp.get_exercise_history("Bench")

        self.assertEqual(history["source_count"], 50)
        self.assertTrue(history["history_may_be_truncated"])

    def test_exercise_history_skips_external_detail_lookup(self):
        detail = {
            "workoutSetActivity": [
                {
                    "movementId": "movement-1",
                    "warmUp": False,
                    "baseWeight": 20,
                    "repCount": 5,
                    "volume": 100,
                    "oneRepMax": 25,
                }
            ]
        }

        def api_get(endpoint, params=None):
            if endpoint.endswith("/activities"):
                return [self.external, self.internal]
            if endpoint.endswith("/workout-activities/internal-1"):
                return detail
            self.fail(f"Unexpected detail request: {endpoint}")

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(
                tonal_mcp,
                "_movement_map",
                return_value={"movement-1": {"name": "Bench Press"}},
            ),
            patch.object(tonal_mcp, "_api_get", side_effect=api_get),
        ):
            history = tonal_mcp.get_exercise_history("Bench")

        self.assertEqual(history["sessions_found"], 1)
        self.assertEqual(history["sessions"][0]["total_volume_lbs"], 100)
        self.assertFalse(history["history_may_be_truncated"])

    def test_detail_tools_return_structured_result_for_404(self):
        def api_get(endpoint, params=None):
            if endpoint.endswith("/activities"):
                return [self.external]
            raise ValueError("Tonal API 404: Not Found")

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", side_effect=api_get),
        ):
            raw = tonal_mcp.get_workout_detail("external-1")
            formatted = tonal_mcp.get_performance_summary("external-1")

        expected = {
            "error": "no_strength_data",
            "activity_id": "external-1",
            "status": 404,
        }
        self.assertEqual(raw, expected)
        self.assertEqual(formatted, expected)

    def test_unknown_activity_404_is_not_classified_as_external(self):
        def api_get(endpoint, params=None):
            if endpoint.endswith("/activities"):
                return [self.external]
            raise ValueError("Tonal API 404: Not Found")

        with (
            patch.object(tonal_mcp, "_uid", return_value="user-1"),
            patch.object(tonal_mcp, "_api_get", side_effect=api_get),
        ):
            result = tonal_mcp.get_workout_detail("unknown-1")

        self.assertEqual(
            result,
            {"error": "activity_not_found", "activity_id": "unknown-1", "status": 404},
        )

    def test_internal_activity_404_is_temporarily_unavailable(self):
        with patch.object(
            tonal_mcp,
            "_api_get",
            side_effect=ValueError("Tonal API 404: Not Found"),
        ):
            result = tonal_mcp._strength_activity_data(
                "/detail", "internal-1", "user-1", activity_type="Internal"
            )

        self.assertEqual(
            result,
            {"error": "detail_unavailable", "activity_id": "internal-1", "status": 404},
        )

    def test_strength_detail_propagates_non_404_errors(self):
        with patch.object(
            tonal_mcp,
            "_api_get",
            side_effect=ValueError("Tonal API 500: unavailable"),
        ):
            with self.assertRaisesRegex(ValueError, "500"):
                tonal_mcp._strength_activity_data("/detail", "activity-1", "user-1")


if __name__ == "__main__":
    unittest.main()
