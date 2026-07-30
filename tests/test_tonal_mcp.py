import importlib.util
import sys
import types
import unittest
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


if __name__ == "__main__":
    unittest.main()
