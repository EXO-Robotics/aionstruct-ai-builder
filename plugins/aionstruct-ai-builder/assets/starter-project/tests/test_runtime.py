from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct_expand import expand  # noqa: E402
from aionstruct_quality import estimate_light_field  # noqa: E402
from aionstruct_validate import load_blueprint_json, validate_blueprint  # noqa: E402
from lib.aionstruct_spatial import connected_component, walkable_floor_cells  # noqa: E402
from lib.mcstructure_le import encode_mcstructure, flat_index  # noqa: E402
from lib.mcstructure_reader import decode_mcstructure_file  # noqa: E402


BLUEPRINT = ROOT / "aionstruct" / "examples" / "wayfarers_hearth_house.aionstruct.json"


class PortableRuntimeTests(unittest.TestCase):
    def test_public_schema_accepts_pack_owned_namespace(self) -> None:
        blueprint = load_blueprint_json(BLUEPRINT)
        blueprint["id"] = "my_pack:structures/roadside_house"
        self.assertEqual([], validate_blueprint(blueprint))

    def test_bedrock_index_is_z_fastest_then_y_then_x(self) -> None:
        self.assertEqual(73, flat_index(2, 0, 3, 5, 7))

    def test_encoder_preserves_explicit_air_and_void(self) -> None:
        cells = [
            {"x": 0, "y": 0, "z": 0, "block": "minecraft:stone"},
            {"x": 1, "y": 0, "z": 0, "block": "minecraft:air"},
        ]
        data, _palette, _indices = encode_mcstructure((3, 1, 1), cells)
        with tempfile.NamedTemporaryFile(suffix=".mcstructure") as handle:
            handle.write(data)
            handle.flush()
            decoded = decode_mcstructure_file(handle.name)
        self.assertEqual("block", decoded["cells"][0]["primary"]["classification"])
        self.assertEqual("air", decoded["cells"][1]["primary"]["classification"])
        self.assertEqual("void", decoded["cells"][2]["primary"]["classification"])

    def test_blueprint_v1_reference_bytes_are_unchanged(self) -> None:
        ir = expand(load_blueprint_json(BLUEPRINT))
        data, _palette, _indices = encode_mcstructure(tuple(ir["size"]), ir["cells"])
        self.assertEqual(
            "6c40899aae4fba51e024f4d5c45879a2be74d4984cfa93d733ffd3234748721c",
            hashlib.sha256(data).hexdigest(),
        )

    def test_example_has_no_walkable_islands(self) -> None:
        ir = expand(load_blueprint_json(BLUEPRINT))
        walkable = walkable_floor_cells(ir, headroom=3)
        anchors = {item["name"]: tuple(item["local"]) for item in ir["anchors"]}
        reached = connected_component(walkable, anchors["approach"], max_step=1)
        self.assertEqual(walkable, reached)

    def test_light_sources_use_maximum_not_sum(self) -> None:
        ir = {"cells": [
            {"x": 0, "y": 1, "z": 0, "block": "minecraft:lantern"},
            {"x": 2, "y": 1, "z": 0, "block": "minecraft:lantern"},
        ]}
        contract = {"lighting": {"emission_by_block": {"minecraft:lantern": 15}}}
        self.assertEqual({(1, 1, 0): 14}, estimate_light_field(ir, contract, {(1, 1, 0)}))


if __name__ == "__main__":
    unittest.main()
