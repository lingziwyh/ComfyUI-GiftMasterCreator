from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NODE_IDS = {
    "GiftMaster_APIConfig",
    "GiftMaster_GenerationSettings",
    "GiftMaster_SkillLoader",
    "GiftMaster_LowCoinGiftTaskBuilder",
    "GiftMaster_HighCoinGiftTaskBuilder",
    "GiftMaster_APISkillExecutor",
    "GiftMaster_H3PromptValidator",
}


def load_plugin_module():
    entry = ROOT / "__init__.py"
    if not entry.is_file():
        raise AssertionError("插件根目录缺少 __init__.py，ComfyUI 无法注册节点。")
    module_name = "giftmastercreator_comfy_plugin"
    spec = importlib.util.spec_from_file_location(
        module_name,
        entry,
        submodule_search_locations=[str(ROOT)],
    )
    if spec is None or spec.loader is None:
        raise AssertionError("无法创建插件入口模块。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


class NodeRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = load_plugin_module()

    def test_expected_nodes_are_registered(self):
        mappings = self.plugin.NODE_CLASS_MAPPINGS
        displays = self.plugin.NODE_DISPLAY_NAME_MAPPINGS
        self.assertTrue(EXPECTED_NODE_IDS <= set(mappings), set(mappings))
        self.assertEqual(set(mappings), set(displays))

    def test_no_local_model_nodes_are_published(self):
        node_ids = set(self.plugin.NODE_CLASS_MAPPINGS)
        forbidden_fragments = ("ModelLoader", "LocalModel", "GGUF", "MMProj", "Unload")
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertFalse(any(fragment.lower() in node_id.lower() for node_id in node_ids), node_ids)

    def test_node_schemas_are_json_serializable_and_match_run_signatures(self):
        for node_id, node_class in self.plugin.NODE_CLASS_MAPPINGS.items():
            with self.subTest(node_id=node_id):
                schema = node_class.INPUT_TYPES()
                json.dumps(schema, ensure_ascii=False)
                self.assertTrue(hasattr(node_class, "RETURN_TYPES"))
                self.assertTrue(hasattr(node_class, "RETURN_NAMES"))
                self.assertEqual(len(node_class.RETURN_TYPES), len(node_class.RETURN_NAMES))
                self.assertTrue(str(node_class.CATEGORY).startswith("GiftMaster"))
                function_name = node_class.FUNCTION
                signature = inspect.signature(getattr(node_class(), function_name))
                accepts_kwargs = any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                )
                for input_name in (*schema.get("required", {}), *schema.get("optional", {})):
                    self.assertTrue(accepts_kwargs or input_name in signature.parameters, input_name)

    def test_socket_contract_for_main_workflow(self):
        mappings = self.plugin.NODE_CLASS_MAPPINGS
        api_config = mappings["GiftMaster_APIConfig"]
        settings = mappings["GiftMaster_GenerationSettings"]
        skill_loader = mappings["GiftMaster_SkillLoader"]
        low_builder = mappings["GiftMaster_LowCoinGiftTaskBuilder"]
        high_builder = mappings["GiftMaster_HighCoinGiftTaskBuilder"]
        executor = mappings["GiftMaster_APISkillExecutor"]
        validator = mappings["GiftMaster_H3PromptValidator"]

        self.assertEqual("GIFTMASTER_API_CONFIG", api_config.RETURN_TYPES[0])
        self.assertEqual("GIFTMASTER_GENERATION_SETTINGS", settings.RETURN_TYPES[0])
        self.assertEqual("GIFTMASTER_SKILL_SELECTION", skill_loader.RETURN_TYPES[0])
        self.assertEqual("STRING", low_builder.RETURN_TYPES[0])
        self.assertEqual("STRING", high_builder.RETURN_TYPES[0])
        self.assertEqual("STRING", executor.RETURN_TYPES[0])
        self.assertEqual("STRING", validator.RETURN_TYPES[0])

        executor_inputs = executor.INPUT_TYPES()
        required = executor_inputs["required"]
        optional = executor_inputs.get("optional", {})
        self.assertEqual("GIFTMASTER_API_CONFIG", required["api_config"][0])
        self.assertEqual("GIFTMASTER_SKILL_SELECTION", required["skill_selection"][0])
        self.assertEqual("STRING", required["task"][0])
        self.assertEqual("GIFTMASTER_GENERATION_SETTINGS", optional["generation_settings"][0])
        for index in range(1, 10):
            name = f"image_{index}"
            self.assertEqual("IMAGE", optional[name][0])

        api_inputs = api_config.INPUT_TYPES()["required"]
        self.assertEqual("GIFTMASTER_API_KEY", api_inputs["api_key_env"][1]["default"])
        self.assertNotIn("direct_api_key", api_inputs)


class SkillManifestTests(unittest.TestCase):
    def test_bundled_skill_manifests_are_complete_and_nonoverlapping(self):
        manifests = []
        for path in sorted((ROOT / "skills").glob("*/giftmaster.json")):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifests.append((path, manifest))
            self.assertEqual(path.parent.name, manifest["id"])
            self.assertEqual(1, manifest["schema_version"])
            self.assertTrue((path.parent / manifest["skill_file"]).is_file())
            self.assertEqual(["T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"], manifest["supported_modes"])
            for relative in manifest["runtime_references"]:
                self.assertTrue((path.parent / relative).is_file(), relative)
            self.assertFalse(set(manifest["runtime_references"]) & set(manifest["evaluation_only_references"]))

        self.assertEqual(2, len(manifests))
        by_id = {manifest["id"]: manifest for _path, manifest in manifests}
        self.assertEqual(
            {"h3-low-coin-gift-director", "h3-live-gift-director"},
            set(by_id),
        )
        low = by_id["h3-low-coin-gift-director"]["price_range"]
        high = by_id["h3-live-gift-director"]["price_range"]
        self.assertEqual((99, 999, 499), (low["minimum"], low["maximum"], low["default"]))
        self.assertEqual((1000, 3000, 2000), (high["minimum"], high["maximum"], high["default"]))


class ExampleWorkflowTests(unittest.TestCase):
    def test_example_workflows_reference_registered_nodes_and_valid_link_slots(self):
        registered = EXPECTED_NODE_IDS | {"LoadImage"}
        for path in sorted((ROOT / "examples" / "workflows").glob("*.json")):
            with self.subTest(path=path.name):
                workflow = json.loads(path.read_text(encoding="utf-8"))
                nodes = {node["id"]: node for node in workflow["nodes"]}
                self.assertTrue(nodes)
                self.assertTrue(all(node["type"] in registered for node in nodes.values()))
                for link_id, _source, _source_slot, target, target_slot, _socket_type in workflow["links"]:
                    self.assertLess(target_slot, len(nodes[target].get("inputs", [])))
                    self.assertEqual(link_id, nodes[target]["inputs"][target_slot]["link"])
                api_nodes = [node for node in nodes.values() if node["type"] == "GiftMaster_APIConfig"]
                self.assertEqual(1, len(api_nodes))
                self.assertIn("GIFTMASTER_API_KEY", api_nodes[0]["widgets_values"])
                self.assertFalse(any(str(value).startswith(("sk-", "ghp_")) for value in api_nodes[0]["widgets_values"]))


if __name__ == "__main__":
    unittest.main()
