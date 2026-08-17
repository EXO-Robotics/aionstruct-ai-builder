from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct_plan import load_plan, lower_plan, validate_plan  # noqa: E402
from aionstruct_validate import validate_blueprint  # noqa: E402


PLAN = ROOT / "aionstruct" / "examples" / "semantic_roadside_house.aionplan.json"


class PlanV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load_plan(PLAN)

    def codes(self, plan: dict) -> set[str]:
        return {item["code"] for item in validate_plan(plan)}

    def test_reference_plan_lowers_to_valid_blueprint(self) -> None:
        self.assertEqual([], validate_plan(self.plan))
        blueprint, source_map = lower_plan(self.plan)
        self.assertEqual([], validate_blueprint(blueprint))
        self.assertTrue(all(op["op"] != "module" for op in blueprint["ops"]))
        covered = [
            index
            for component in source_map["components"]
            for index in component["blueprint_op_indices"]
        ]
        self.assertEqual(list(range(len(blueprint["ops"]))), covered)

    def test_lowering_is_canonical_across_component_array_order(self) -> None:
        blueprint_a, source_map_a = lower_plan(self.plan)
        reversed_plan = copy.deepcopy(self.plan)
        reversed_plan["components"].reverse()
        blueprint_b, source_map_b = lower_plan(reversed_plan)
        self.assertEqual(blueprint_a, blueprint_b)
        self.assertEqual(source_map_a["topological_order"], source_map_b["topological_order"])

    def test_duplicate_id_is_structured(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][1]["id"] = broken["components"][0]["id"]
        diagnostic = next(item for item in validate_plan(broken) if item["code"] == "PLAN_DUPLICATE_ID")
        self.assertEqual("error", diagnostic["severity"])
        self.assertIn("component_id", diagnostic)
        self.assertTrue(diagnostic["path"].startswith("$.components"))

    def test_missing_dependency_fails_closed(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][1]["depends_on"] = ["missing"]
        self.assertIn("PLAN_UNKNOWN_DEPENDENCY", self.codes(broken))

    def test_invalid_dependency_type_returns_diagnostic_not_exception(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][1]["depends_on"] = [{"not": "an id"}]
        self.assertIn("PLAN_DEPENDENCY_TYPE", self.codes(broken))

    def test_invalid_host_and_kind_types_return_diagnostics(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][2]["host"] = {"not": "an id"}
        broken["components"][3]["opening_kind"] = ["window"]
        self.assertIn("PLAN_HOST_TYPE", self.codes(broken))
        self.assertIn("PLAN_OPENING_KIND", self.codes(broken))

    def test_dependency_cycle_fails_closed(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][0]["depends_on"] = ["hall"]
        self.assertIn("PLAN_DEPENDENCY_CYCLE", self.codes(broken))

    def test_host_must_be_an_explicit_dependency(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][2]["depends_on"] = []
        self.assertIn("PLAN_HOST_DEPENDENCY", self.codes(broken))

    def test_host_must_reference_a_room(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][2]["host"] = "base"
        broken["components"][2]["depends_on"] = ["base"]
        self.assertIn("PLAN_HOST_KIND", self.codes(broken))

    def test_opening_must_lie_on_its_host_wall(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][2]["wall_z"] = 4
        self.assertIn("PLAN_OPENING_HOST_WALL", self.codes(broken))

    def test_roof_must_cover_and_start_above_host(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][4]["from"] = [6, 10, 6]
        self.assertIn("PLAN_ROOF_HOST_HEIGHT", self.codes(broken))
        self.assertIn("PLAN_ROOF_HOST_SPAN", self.codes(broken))

    def test_room_requires_a_real_interior(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["components"][1]["to"] = [6, 4, 6]
        self.assertIn("PLAN_ROOM_INTERIOR", self.codes(broken))

    def test_unimplemented_transforms_fail_closed(self) -> None:
        broken = copy.deepcopy(self.plan)
        broken["rotation_policy"] = "y_90"
        self.assertIn("PLAN_TRANSFORM_UNSUPPORTED", self.codes(broken))

    def test_stair_run_component_lowers_without_expanding_plan_vocabulary(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["components"].append(
            {
                "id": "loft_stair",
                "kind": "stair_run",
                "depends_on": ["hall"],
                "at": [7, 4, 14],
                "steps": 4,
                "facing": "north",
                "block": "planks"
            }
        )
        blueprint, _source_map = lower_plan(plan)
        self.assertEqual("stair", next(op["op"] for op in blueprint["ops"] if "loft_stair" in op.get("comment", "")))

    def test_source_map_hashes_are_stable(self) -> None:
        blueprint_a, map_a = lower_plan(self.plan)
        blueprint_b, map_b = lower_plan(json.loads(json.dumps(self.plan)))
        self.assertEqual(blueprint_a, blueprint_b)
        self.assertEqual(map_a, map_b)


if __name__ == "__main__":
    unittest.main()
