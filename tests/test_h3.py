from __future__ import annotations

import unittest

from giftmaster.errors import GiftMasterError
from giftmaster.h3 import validate_h3_prompt
from giftmaster.tasks import validate_image_count


VALID_LOW_T2VA = """integrated_multimodal_description: [Shot 1] In a 1:1 frame, a stylized paper crane enters, makes one clean arc, and exits against a uniform solid-color background whose color and brightness remain unchanged throughout, all in a single continuous shot.

overall_soundscape: N/A

non_diegetic_music: N/A"""

SCENE_T2VA = """integrated_multimodal_description: [Shot 1] In a 1:1 frame, a stylized paper crane enters a compact moonlit room, turns once, and exits in a single continuous shot.

overall_soundscape: N/A

non_diegetic_music: N/A"""


class H3ImageCountTests(unittest.TestCase):
    def test_image_count_matrix(self):
        matrix = {
            "T2VA": {0: True, 1: False},
            "I2VA": {0: False, 1: True, 2: False},
            "FL2VA": {1: False, 2: True, 3: False},
            "L2VA": {0: False, 1: True, 2: False},
            "Ref2VA": {0: False, 1: True, 9: True, 10: False},
        }
        for mode, cases in matrix.items():
            for count, expected in cases.items():
                with self.subTest(mode=mode, count=count):
                    if expected:
                        validate_image_count(mode, count)
                    else:
                        with self.assertRaises(GiftMasterError):
                            validate_image_count(mode, count)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(GiftMasterError, "模式"):
            validate_image_count("UNKNOWN", 0)


class LowCoinH3RuleTests(unittest.TestCase):
    def _validate(self, prompt: str, *, price: int = 299, aspect: str = "1:1"):
        return validate_h3_prompt(
            prompt,
            mode="T2VA",
            duration=73 / 24 if price <= 299 else 90 / 24,
            image_count=0,
            profile="LOW_COIN_GIFT",
            gift_price=price,
            aspect_ratio=aspect,
        )

    def assertInvalid(self, prompt: str, expected_text: str, *, price: int = 299, aspect: str = "1:1"):
        result = self._validate(prompt, price=price, aspect=aspect)
        self.assertTrue(any(expected_text in error for error in result.errors), result.errors)

    def test_valid_single_shot_silent_solid_background(self):
        result = self._validate(VALID_LOW_T2VA)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)
        self.assertEqual([], result.warnings)
        self.assertEqual(VALID_LOW_T2VA, result.cleaned)

    def test_requires_exactly_one_shot_one(self):
        two_shots = VALID_LOW_T2VA.replace(
            "all in a single continuous shot.",
            "[Shot 2] At 00:01.500, it exits.",
        )
        self.assertInvalid(two_shots, "单镜头")

        duplicate = VALID_LOW_T2VA.replace(
            "overall_soundscape:",
            "[Shot 1] The crane continues moving.\n\n" "overall_soundscape:",
        )
        self.assertInvalid(duplicate, "恰好")

    def test_rejects_cut_language(self):
        prompt = VALID_LOW_T2VA.replace("makes one clean arc", "makes one clean arc, then the camera cuts to a close-up")
        self.assertInvalid(prompt, "切镜")

    def test_requires_both_audio_fields_to_be_exactly_na(self):
        sound = VALID_LOW_T2VA.replace("overall_soundscape: N/A", "overall_soundscape: A soft whoosh")
        self.assertInvalid(sound, "N/A")
        music = VALID_LOW_T2VA.replace("non_diegetic_music: N/A", "non_diegetic_music: Soft strings")
        self.assertInvalid(music, "N/A")

    def test_rejects_dialogue_audio_labels_and_speaker_ids(self):
        for token in ("<d>[Chinese] 你好！</d>", "<Audio 1>", "(S1)"):
            with self.subTest(token=token):
                prompt = VALID_LOW_T2VA.replace("makes one clean arc", f"makes one clean arc {token}")
                self.assertInvalid(prompt, "静音")

    def test_sub_500_requires_solid_and_unchanged_background(self):
        self.assertInvalid(SCENE_T2VA, "纯色", price=499)
        unstable = VALID_LOW_T2VA.replace("whose color and brightness remain unchanged throughout", "that shifts hue throughout")
        self.assertInvalid(unstable, "保持不变", price=499)

    def test_500_and_above_may_use_a_compact_scene(self):
        result = self._validate(SCENE_T2VA, price=500)
        self.assertTrue(result.valid, result.errors)

    def test_expected_aspect_is_enforced(self):
        self.assertInvalid(VALID_LOW_T2VA, "画幅", aspect="4:3")


class GenericH3FormatTests(unittest.TestCase):
    def test_forbids_watermark_flag(self):
        result = validate_h3_prompt(
            VALID_LOW_T2VA + "\n--wm false",
            mode="T2VA",
            duration=73 / 24,
            image_count=0,
        )
        self.assertTrue(any("--wm false" in error for error in result.errors), result.errors)

    def test_missing_or_duplicate_core_fields_fail(self):
        missing = VALID_LOW_T2VA.replace("\n\nnon_diegetic_music: N/A", "")
        result = validate_h3_prompt(missing, mode="T2VA", duration=73 / 24)
        self.assertTrue(any("non_diegetic_music" in error for error in result.errors), result.errors)

        duplicate = VALID_LOW_T2VA + "\n\noverall_soundscape: N/A"
        result = validate_h3_prompt(duplicate, mode="T2VA", duration=73 / 24)
        self.assertTrue(any("重复" in error for error in result.errors), result.errors)

    def test_auto_detects_all_endpoint_alignment_modes(self):
        body = """integrated_multimodal_description: [Shot 1] 1:1. A single continuous action.
overall_soundscape: N/A
non_diegetic_music: N/A"""
        cases = {
            "I2VA": "For the target video, <Picture 1> aligns with the 0.00-second first frame.",
            "FL2VA": "Picture 1 aligns with 0.00 seconds and Picture 2 aligns with the 3.75-second last frame.",
            "L2VA": "<Picture 1> aligns with the 3.75-second last frame of the target video.",
        }
        for expected, header in cases.items():
            with self.subTest(mode=expected):
                result = validate_h3_prompt(header + "\n" + body, mode="auto", duration=3.75)
                self.assertTrue(result.valid, result.errors)
                self.assertEqual(expected, result.detected_mode)


if __name__ == "__main__":
    unittest.main()
