from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct import inspect_layers, inspect_materials, structural_diff, structural_fingerprint  # noqa: E402


BLUEPRINT = ROOT / "aionstruct" / "examples" / "wayfarers_hearth_house.aionstruct.json"


class InspectionTests(unittest.TestCase):
    def test_material_and_layer_reports_are_complete(self) -> None:
        materials = inspect_materials(BLUEPRINT)
        layers = inspect_layers(BLUEPRINT)
        self.assertEqual(materials["explicit_cells"], sum(materials["block_counts"].values()))
        self.assertEqual(layers["size"][1], len(layers["layers"]))
        layer_volume = layers["size"][0] * layers["size"][2]
        self.assertTrue(
            all(item["explicit_cells"] + item["void_cells"] == layer_volume for item in layers["layers"])
        )

    def test_fingerprint_is_stable(self) -> None:
        self.assertEqual(
            structural_fingerprint(BLUEPRINT)["sha256"],
            structural_fingerprint(BLUEPRINT)["sha256"],
        )

    def test_diff_reports_identity_and_cell_changes(self) -> None:
        self.assertTrue(structural_diff(BLUEPRINT, BLUEPRINT)["identical"])
        changed = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
        changed["ops"][0]["block"] = "minecraft:gold_block"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as handle:
            json.dump(changed, handle)
            handle.flush()
            report = structural_diff(BLUEPRINT, Path(handle.name))
        self.assertFalse(report["identical"])
        self.assertGreater(report["changed_cell_count"], 0)
        self.assertLessEqual(len(report["changed_cell_samples"]), report["sample_limit"])


if __name__ == "__main__":
    unittest.main()
