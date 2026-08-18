from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct import (  # noqa: E402
    inspect_layers,
    inspect_materials,
    portfolio_audit,
    _normalized_topology,
    structural_diff,
    structural_fingerprint,
    topology_fingerprint,
)


BLUEPRINT = ROOT / "aionstruct" / "examples" / "wayfarers_hearth_house.aionstruct.json"
SEMANTIC = ROOT / "build" / "semantic_roadside_house.blueprint.json"
PORTFOLIO = ROOT / "aionstruct" / "examples" / "example_portfolio.aionportfolio.json"


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

    def test_topology_ignores_palette_but_preserves_air_void_geometry(self) -> None:
        changed = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
        for key, value in list(changed["palette"].items()):
            if isinstance(value, str) and value != "minecraft:air":
                changed["palette"][key] = "minecraft:gold_block"
            elif isinstance(value, dict) and value.get("block") != "minecraft:air":
                value.clear()
                value["block"] = "minecraft:gold_block"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as handle:
            json.dump(changed, handle)
            handle.flush()
            recolored = topology_fingerprint(Path(handle.name))
        original = topology_fingerprint(BLUEPRINT)
        self.assertEqual(original["sha256"], recolored["sha256"])
        self.assertGreater(original["explicit_air_cells"], 0)
        self.assertEqual(original["algorithm"], "sha256-normalized-xz-dihedral-air-solid-topology")

    def test_topology_is_translation_rotation_and_reflection_invariant(self) -> None:
        cells = [
            {"x": 2, "y": 4, "z": 5, "block": "minecraft:stone"},
            {"x": 3, "y": 4, "z": 5, "block": "minecraft:air"},
            {"x": 2, "y": 5, "z": 7, "block": "minecraft:stone"},
        ]
        transformed = [
            {**cell, "x": -cell["z"] + 30, "y": cell["y"] + 8, "z": -cell["x"] + 40}
            for cell in cells
        ]
        self.assertEqual(_normalized_topology(cells), _normalized_topology(transformed))

    def test_portfolio_passes_distinct_examples_and_fails_a_clone(self) -> None:
        report = portfolio_audit([BLUEPRINT, SEMANTIC], PORTFOLIO)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["counts"]["distinct_topologies"], 2)
        clone = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
        clone["id"] = "example:drafts/recolored_clone"
        clone["palette"] = {
            key: ("minecraft:gold_block" if value != "minecraft:air" else value)
            for key, value in clone["palette"].items()
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as handle:
            json.dump(clone, handle)
            handle.flush()
            failed = portfolio_audit([BLUEPRINT, Path(handle.name)])
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["counts"]["duplicate_topology_groups"], 1)
        clone_row = next(row for row in failed["structures"] if row["structure_id"] == "example:drafts/recolored_clone")
        self.assertEqual(clone_row["path"], f"external/{Path(handle.name).name}")

    def test_portfolio_rejects_malformed_purpose_and_repeated_axes(self) -> None:
        contract = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
        contract["structures"][0]["purpose"] = "not an object"
        contract["structures"][1]["distinctness_axes"] = ["silhouette", "silhouette", "traversal"]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as handle:
            json.dump(contract, handle)
            handle.flush()
            report = portfolio_audit([BLUEPRINT, SEMANTIC], Path(handle.name))
        codes = {error["code"] for error in report["errors"]}
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_purpose_object", codes)
        self.assertIn("invalid_distinctness_axes", codes)


if __name__ == "__main__":
    unittest.main()
