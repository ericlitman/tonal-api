import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FastMCP:
    def __init__(self, *args, **kwargs):
        pass

    def tool(self):
        return lambda function: function

    def run(self):
        pass


def load_module(name, relative_path):
    module_path = Path(__file__).parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tonal_mcp():
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = FastMCP

    with patch.dict(sys.modules, {
        "mcp": mcp_module,
        "mcp.server": server_module,
        "mcp.server.fastmcp": fastmcp_module,
    }):
        return load_module("tonal_mcp", Path("mcp") / "tonal_mcp.py")


def load_tonal_tool():
    return load_module("tonal_tool", Path("tonal_tool.py"))


class EstimateDurationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tonal_mcp = load_tonal_mcp()

    def test_posts_bare_array_with_create_workout_set_serialization(self):
        movements = {
            "alternating": {"countReps": True, "isAlternating": True},
            "duration": {"countReps": False},
            "explicit-duration": {"countReps": True},
        }
        blocks = [{"exercises": [
            {
                "movement_id": "alternating",
                "sets": 1,
                "reps": 7,
                "spotter": True,
                "eccentric": True,
                "chains": True,
                "warm_up": True,
                "burnout": True,
                "drop_set": True,
                "weight_percentage": 50,
            },
            {"movement_id": "duration", "sets": 1, "duration": 45},
            {"movement_id": "explicit-duration", "sets": 1, "duration": 20},
        ]}]
        calls = []

        def api_post(endpoint, body):
            calls.append((endpoint, body))
            if endpoint == "/v6/user-workouts":
                return {"id": "workout-id"}
            return {"duration": 52}

        with patch.object(self.tonal_mcp, "_movement_map", return_value=movements), \
                patch.object(self.tonal_mcp, "_api_post", side_effect=api_post):
            create_result = self.tonal_mcp.create_workout("Test Workout", blocks)
            estimate_result = self.tonal_mcp.estimate_duration(blocks)

        self.assertEqual(create_result, {
            "status": "pushed",
            "workout_id": "workout-id",
            "title": "Test Workout",
            "set_count": 3,
        })
        self.assertEqual(estimate_result, {
            "estimated_duration_sec": 52,
            "estimated_duration_min": 0.9,
            "set_count": 3,
        })
        self.assertEqual(calls[0][0], "/v6/user-workouts")
        self.assertEqual(calls[0][1]["title"], "Test Workout")
        self.assertEqual(calls[1][0], "/v6/user-workouts/estimate")
        self.assertIsInstance(calls[1][1], list)
        self.assertEqual(calls[1][1], calls[0][1]["sets"])

        alternating_set, duration_set, explicit_duration_set = calls[1][1]
        self.assertEqual(alternating_set["prescribedReps"], 14)
        self.assertEqual(alternating_set["weightPercentage"], 50)
        for field in ("spotter", "eccentric", "chains", "warmUp", "burnout", "dropSet"):
            self.assertTrue(alternating_set[field])
        self.assertEqual(duration_set["prescribedDuration"], 45)
        self.assertEqual(duration_set["prescribedResistanceLevel"], 5)
        self.assertEqual(explicit_duration_set["prescribedDuration"], 20)
        self.assertEqual(explicit_duration_set["prescribedResistanceLevel"], 5)

    def test_missing_duration_returns_none_fields(self):
        blocks = [{"exercises": [{"movement_id": "movement", "sets": 1, "reps": 7}]}]

        with patch.object(self.tonal_mcp, "_movement_map", return_value={"movement": {"countReps": True}}), \
                patch.object(self.tonal_mcp, "_api_post", return_value={}):
            result = self.tonal_mcp.estimate_duration(blocks)

        self.assertEqual(result, {
            "estimated_duration_sec": None,
            "estimated_duration_min": None,
            "set_count": 1,
        })

    def test_create_workout_still_rejects_invalid_movements_before_posting(self):
        with patch.object(self.tonal_mcp, "_movement_map", return_value={}), \
                patch.object(self.tonal_mcp, "_api_post") as api_post:
            result = self.tonal_mcp.create_workout(
                "Invalid Workout",
                [{"exercises": [{"movement_id": "missing"}]}],
            )

        self.assertEqual(result, {"error": "Invalid movement IDs", "invalid": ["missing"]})
        api_post.assert_not_called()


class CliEstimateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tonal_tool = load_tonal_tool()

    def test_posts_bare_array_with_create_workout_set_serialization(self):
        movements = {
            "alternating": {"countReps": True, "isAlternating": True},
            "duration": {"countReps": False},
            "explicit-duration": {"countReps": True},
        }
        spec = {"title": "Test Workout", "blocks": [{"exercises": [
            {
                "movement_id": "alternating",
                "sets": 1,
                "reps": 7,
                "spotter": True,
                "eccentric": True,
                "chains": True,
                "warm_up": True,
                "burnout": True,
                "drop_set": True,
                "weight_percentage": 50,
            },
            {"movement_id": "duration", "sets": 1, "duration": 45},
            {"movement_id": "explicit-duration", "sets": 1, "duration": 20},
        ]}]}
        calls = []

        def api_post(endpoint, body):
            calls.append((endpoint, body))
            if endpoint == "/v6/user-workouts":
                return {"id": "workout-id"}
            return {"duration": 52}

        args = [json.dumps(spec)]
        with patch.object(self.tonal_tool, "_get_movement_map", return_value=movements), patch.object(
                self.tonal_tool, "api_post", side_effect=api_post):
            create_result = self.tonal_tool.cmd_create_workout(args)
            estimate_result = self.tonal_tool.cmd_estimate(args)

        self.assertEqual(create_result, {
            "status": "pushed",
            "workout_id": "workout-id",
            "title": "Test Workout",
            "set_count": 3,
            "exercise_count": 3,
        })
        self.assertEqual(estimate_result, {
            "estimated_duration_sec": 52,
            "estimated_duration_min": 0.9,
            "set_count": 3,
        })
        self.assertEqual(calls[0][0], "/v6/user-workouts")
        self.assertEqual(calls[1][0], "/v6/user-workouts/estimate")
        self.assertIsInstance(calls[1][1], list)
        self.assertEqual(calls[1][1], calls[0][1]["sets"])

    def test_missing_duration_returns_none_fields(self):
        spec = {"blocks": [{"exercises": [
            {"movement_id": "movement", "sets": 1, "reps": 7},
        ]}]}

        with patch.object(self.tonal_tool, "_get_movement_map",
                          return_value={"movement": {"countReps": True}}), patch.object(
                self.tonal_tool, "api_post", return_value={}):
            result = self.tonal_tool.cmd_estimate([json.dumps(spec)])

        self.assertEqual(result, {
            "estimated_duration_sec": None,
            "estimated_duration_min": None,
            "set_count": 1,
        })


if __name__ == "__main__":
    unittest.main()
