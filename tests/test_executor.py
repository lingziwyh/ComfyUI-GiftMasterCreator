from __future__ import annotations

import json
import unittest
from unittest import mock

from giftmaster.api import APIConfig, GenerationSettings
from giftmaster.errors import SkillError, ValidationError
from giftmaster.executor import run_skill_api
from giftmaster.tasks import build_high_coin_task, build_low_coin_task


LOW_VALID = """integrated_multimodal_description: [Shot 1] 1:1 composition. A paper crane completes one clear arc on a uniform solid-color background that remains unchanged for the entire video.
overall_soundscape: N/A
non_diegetic_music: N/A"""


class FakeClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete(self, system_prompt, user_prompt, image_data_urls=(), settings=None):
        self.calls.append((system_prompt, user_prompt, list(image_data_urls), settings))
        return self.outputs.pop(0), {"requests": 1, "usage": {"total_tokens": 42}}


class ExecutorTests(unittest.TestCase):
    def config(self):
        return APIConfig(base_url="http://127.0.0.1:1/v1", model="unit-model", no_auth=True)

    def test_routes_low_skill_without_a_classifier_request(self):
        task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode="T2VA")
        client = FakeClient([LOW_VALID])
        prompt, report_json = run_skill_api(
            self.config(),
            "auto",
            task,
            client=client,
            settings=GenerationSettings(max_output_tokens=512),
        )
        report = json.loads(report_json)
        self.assertEqual(LOW_VALID, prompt)
        self.assertEqual("h3-low-coin-gift-director", report["skill_id"])
        self.assertEqual(1, len(client.calls))
        self.assertNotIn("api_key", report_json.lower())

    def test_price_notice_is_removed_from_downstream_prompt(self):
        task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode="T2VA")
        client = FakeClient(["价效提示：主体较复杂，将压缩次要装饰。\n" + LOW_VALID])
        prompt, report_json = run_skill_api(self.config(), "auto", task, client=client)
        self.assertEqual(LOW_VALID, prompt)
        self.assertIn("价效提示", json.loads(report_json)["price_effect_notice"])

    def test_repairs_once_and_validates_repaired_result(self):
        task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode="T2VA")
        invalid = LOW_VALID.replace("overall_soundscape: N/A", "overall_soundscape: bells")
        client = FakeClient([invalid, LOW_VALID])
        _prompt, report_json = run_skill_api(self.config(), "auto", task, client=client, repair_attempts=1)
        report = json.loads(report_json)
        self.assertEqual(2, len(client.calls))
        self.assertEqual(1, report["repair_attempts"])
        self.assertTrue(report["validation_passed"])
        self.assertEqual(84, report["usage"]["total_tokens"])

    def test_failed_repair_never_returns_an_invalid_prompt(self):
        task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode="T2VA")
        invalid = LOW_VALID.replace("overall_soundscape: N/A", "overall_soundscape: bells")
        client = FakeClient([invalid, invalid])
        with self.assertRaises(ValidationError):
            run_skill_api(self.config(), "auto", task, client=client, repair_attempts=1)

    def test_fixed_skill_conflict_fails_before_network(self):
        task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode="T2VA")
        client = FakeClient([LOW_VALID])
        with self.assertRaises(SkillError):
            run_skill_api(self.config(), "h3-live-gift-director", task, client=client)
        self.assertEqual([], client.calls)

    def test_ref2va_uses_images_in_input_order(self):
        task, _frames, _seconds = build_high_coin_task("星海", reference_mode="Ref2VA")
        result = """subject_definitions:
<Picture 1>: a silver emblem.
<Subject 1>: the emblem.
summary: [reference generation] reference-to-video live gift.
retention_analysis:
<Picture 1>: fully_preserved - preserve source composition.
<Subject 1>: fully_preserved - preserve identity.
detailed_description: [Shot 1] 1:1. <Subject 1> rises through a continuous halo.
overall_soundscape: N/A
non_diegetic_music: N/A"""
        image = "data:image/jpeg;base64,AA=="
        client = FakeClient([result])
        with mock.patch("giftmaster.executor.encode_image_data_urls", return_value=[image]):
            prompt, report = run_skill_api(self.config(), "auto", task, image_inputs=[object()], client=client)
        self.assertEqual(result, prompt)
        self.assertEqual([image], client.calls[0][2])
        self.assertEqual("LIVE_GIFT", json.loads(report)["profile"])

    def test_endpoint_alignment_header_survives_notice_cleanup(self):
        cases = {
            "I2VA": "For the target video, <Picture 1> aligns with the 0.00-second first frame.",
            "FL2VA": "Picture 1 aligns with 0.00 seconds and Picture 2 aligns with the 3.75-second last frame of the target video.",
            "L2VA": "<Picture 1> aligns with the 3.75-second last frame of the target video.",
        }
        for mode, header in cases.items():
            with self.subTest(mode=mode):
                task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode=mode)
                output = "价效提示：压缩次要装饰。\n" + header + "\n" + LOW_VALID
                client = FakeClient([output])
                count = 2 if mode == "FL2VA" else 1
                urls = [f"data:image/jpeg;base64,{index}" for index in range(count)]
                with mock.patch("giftmaster.executor.encode_image_data_urls", return_value=urls):
                    prompt, report_json = run_skill_api(
                        self.config(), "auto", task, image_inputs=[object()] * count, client=client
                    )
                self.assertTrue(prompt.startswith(header), prompt)
                self.assertNotIn("价效提示", prompt)
                self.assertIn("价效提示", json.loads(report_json)["price_effect_notice"])


if __name__ == "__main__":
    unittest.main()
