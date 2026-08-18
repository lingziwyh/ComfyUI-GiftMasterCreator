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
    "GiftMaster_GiftTaskBuilder",
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
        universal_builder = mappings["GiftMaster_GiftTaskBuilder"]
        low_builder = mappings["GiftMaster_LowCoinGiftTaskBuilder"]
        high_builder = mappings["GiftMaster_HighCoinGiftTaskBuilder"]
        executor = mappings["GiftMaster_APISkillExecutor"]
        validator = mappings["GiftMaster_H3PromptValidator"]

        self.assertEqual("GIFTMASTER_API_CONFIG", api_config.RETURN_TYPES[0])
        self.assertEqual("GIFTMASTER_GENERATION_SETTINGS", settings.RETURN_TYPES[0])
        self.assertEqual("GIFTMASTER_SKILL_SELECTION", skill_loader.RETURN_TYPES[0])
        self.assertEqual(
            ("STRING", "INT", "FLOAT", "GIFTMASTER_SKILL_SELECTION"),
            universal_builder.RETURN_TYPES,
        )
        self.assertEqual(("任务", "H3帧数", "实际时长", "Skill路由"), universal_builder.RETURN_NAMES)
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
        self.assertEqual(
            ["api_key", "bearer", "bytedance_compat"],
            api_inputs["azure_auth"][0],
        )
        self.assertEqual("api_key", api_inputs["azure_auth"][1]["default"])
        self.assertNotIn("direct_api_key", api_inputs)

        universal_inputs = universal_builder.INPUT_TYPES()["required"]
        self.assertEqual(99, universal_inputs["gift_price"][1]["min"])
        self.assertEqual(3000, universal_inputs["gift_price"][1]["max"])
        self.assertTrue(
            {"target_duration", "shot_structure", "sound_design"} <= set(universal_inputs),
            set(universal_inputs),
        )

    def test_frontend_contract_keeps_all_backend_images_and_progressively_reveals_them(self):
        executor = self.plugin.NODE_CLASS_MAPPINGS["GiftMaster_APISkillExecutor"]
        optional = executor.INPUT_TYPES().get("optional", {})
        self.assertEqual(
            [f"image_{index}" for index in range(1, 10)],
            [name for name in optional if name.startswith("image_")],
        )

        web_directory = getattr(self.plugin, "WEB_DIRECTORY", "")
        self.assertTrue(web_directory, "插件必须声明 WEB_DIRECTORY 以加载渐进图片输入脚本。")
        web_root = (ROOT / web_directory).resolve()
        self.assertTrue(web_root.is_dir(), web_root)
        scripts = sorted(web_root.glob("*.js"))
        self.assertTrue(scripts, web_root)
        source = "\n".join(path.read_text(encoding="utf-8") for path in scripts)

        required_fragments = (
            "GiftMaster_APISkillExecutor",
            "FIRST_IMAGE = 1",
            "LAST_IMAGE = 9",
            "IMAGE_INPUT_PATTERN",
            "image_${index}",
            "onConnectionsChange",
            "afterConfigureGraph",
            "configuringGraph",
            "subgraphs",
            "addInput",
            "removeInput",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)
        self.assertRegex(source, r"\.link\b")
        self.assertTrue("queueMicrotask" in source or "requestAnimationFrame" in source)

    def test_chinese_localization_covers_every_published_node_and_input(self):
        locale_path = ROOT / "locales" / "zh" / "nodeDefs.json"
        self.assertTrue(locale_path.is_file(), locale_path)
        locale = json.loads(locale_path.read_text(encoding="utf-8"))
        self.assertEqual(EXPECTED_NODE_IDS, set(locale))

        untranslated_ratio = {"", "1:1", "4:3", "9:16", "16:9", "3:4"}
        for node_id, node_class in self.plugin.NODE_CLASS_MAPPINGS.items():
            with self.subTest(node_id=node_id):
                translated = locale[node_id]
                self.assertTrue(translated.get("display_name"))
                self.assertTrue(translated.get("description"))
                translated_inputs = translated.get("inputs", {})
                schema = node_class.INPUT_TYPES()
                for input_name, config in {
                    **schema.get("required", {}),
                    **schema.get("optional", {}),
                }.items():
                    with self.subTest(node_id=node_id, input_name=input_name):
                        self.assertIn(input_name, translated_inputs)
                        self.assertTrue(translated_inputs[input_name].get("name"))
                        self.assertTrue(translated_inputs[input_name].get("tooltip"))
                        self.assertGreaterEqual(len(config), 2)
                        self.assertTrue(config[1].get("tooltip"))
                        if config[0] == "BOOLEAN":
                            self.assertTrue(config[1].get("label_on"))
                            self.assertTrue(config[1].get("label_off"))
                        if isinstance(config[0], list):
                            options = translated_inputs[input_name].get("options", {})
                            required_options = set(config[0]) - untranslated_ratio
                            if input_name == "skill":
                                required_options &= {
                                    "auto",
                                    "h3-low-coin-gift-director",
                                    "h3-live-gift-director",
                                }
                            self.assertTrue(required_options <= set(options), (input_name, required_options, options))

                outputs = translated.get("outputs", {})
                self.assertEqual(len(node_class.RETURN_TYPES), len(outputs))
                for index in range(len(node_class.RETURN_TYPES)):
                    self.assertTrue(outputs[str(index)].get("name"))
                    self.assertTrue(outputs[str(index)].get("tooltip"))


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

    def test_universal_example_routes_task_and_skill_without_a_skill_loader(self):
        path = ROOT / "examples" / "workflows" / "universal-auto-t2va-api.json"
        workflow = json.loads(path.read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        universal = next(node for node in nodes.values() if node["type"] == "GiftMaster_GiftTaskBuilder")
        executor = next(node for node in nodes.values() if node["type"] == "GiftMaster_APISkillExecutor")

        self.assertFalse(any(node["type"] == "GiftMaster_SkillLoader" for node in nodes.values()))
        links = {link[0]: link for link in workflow["links"]}
        task_link_id = universal["outputs"][0]["links"][0]
        skill_link_id = universal["outputs"][3]["links"][0]
        self.assertEqual((universal["id"], 0, executor["id"], 2, "STRING"), tuple(links[task_link_id][1:]))
        self.assertEqual(
            (universal["id"], 3, executor["id"], 1, "GIFTMASTER_SKILL_SELECTION"),
            tuple(links[skill_link_id][1:]),
        )


if __name__ == "__main__":
    unittest.main()
