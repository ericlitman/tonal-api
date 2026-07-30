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
                    "warmUp": True,
                },
                {
                    "movementId": "straight-bar",
                    "repCount": 6,
                    "baseWeight": 42,
                    "volume": 100,
                    "oneRepMax": 52.36,
                    "suggestedWeight": 49.39,
                    "warmUp": False,
                },
                {
                    "movementId": "handles",
                    "repCount": 6,
                    "baseWeight": 30,
                    "volume": 60,
                    "oneRepMax": 38,
                    "suggestedWeight": 32,
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
        self.assertEqual(straight_bar["working_volume_lbs"], 100)
        self.assertEqual(straight_bar["warmup_volume_lbs"], 50)
        self.assertEqual(straight_bar["total_volume_lbs"], 150)

        self.assertEqual(handles["set_details"][0]["weight_lbs"], 30)
        self.assertEqual(handles["set_details"][0]["one_rep_max"], 38)
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
