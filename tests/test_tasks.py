from __future__ import annotations

import unittest

from giftmaster.errors import GiftMasterError
from giftmaster.tasks import build_high_coin_task, build_low_coin_task


class LowCoinTaskTests(unittest.TestCase):
    def _build(self, price: int, *, mode: str = "T2VA", aspect_ratio: str = "1:1"):
        return build_low_coin_task(
            gift_name="纸鹤问候",
            gift_price=price,
            creative_brief="纸鹤沿一条清晰弧线进场，完成一次动作后退场",
            reference_mode=mode,
            aspect_ratio=aspect_ratio,
            extra_constraints="",
        )

    def test_price_duration_and_frame_boundaries(self):
        cases = {
            99: (3.0, 73, 73 / 24),
            299: (3.0, 73, 73 / 24),
            300: (4.0, 90, 90 / 24),
            499: (4.0, 90, 90 / 24),
            500: (4.0, 90, 90 / 24),
            999: (4.0, 90, 90 / 24),
        }
        for price, (nominal, expected_frames, expected_duration) in cases.items():
            with self.subTest(price=price):
                task, frames, duration = self._build(price)
                self.assertEqual(expected_frames, frames)
                self.assertAlmostEqual(expected_duration, duration)
                self.assertIn("[GMC_TASK_SCHEMA=1]", task)
                self.assertIn("[GMC_PROFILE=LOW_COIN_GIFT]", task)
                self.assertIn("[GMC_H3_MODE=T2VA]", task)
                self.assertIn("[GMC_SKILL_ID=h3-low-coin-gift-director]", task)
                self.assertIn(f"[GMC_GIFT_PRICE={price}]", task)
                self.assertIn(f"[GMC_H3_FRAMES={expected_frames}]", task)
                self.assertIn(f"有效时长 {expected_duration:.6f} 秒", task)
                self.assertIn("恰好一个连续镜头", task)
                self.assertIn("全程静音", task)

    def test_rejects_prices_outside_99_to_999(self):
        for price in (98, 1000):
            with self.subTest(price=price), self.assertRaisesRegex(GiftMasterError, "99.*999"):
                self._build(price)

    def test_default_price_is_499(self):
        task, frames, duration = build_low_coin_task(gift_name="默认档礼物")
        self.assertIn("[GMC_GIFT_PRICE=499]", task)
        self.assertEqual(90, frames)
        self.assertAlmostEqual(90 / 24, duration)

    def test_rejects_unsupported_aspect(self):
        with self.assertRaisesRegex(GiftMasterError, "1:1.*4:3"):
            self._build(499, aspect_ratio="9:16")

    def test_background_boundary_is_explicit_in_task(self):
        below_500, _, _ = self._build(499)
        self.assertIn("纯色背景", below_500)
        self.assertIn("全程", below_500)
        self.assertIn("不变", below_500)
        self.assertNotIn("固定颜色", below_500)
        self.assertNotRegex(below_500, r"#[0-9A-Fa-f]{6}")

        at_500, _, _ = self._build(500)
        self.assertRegex(at_500, r"小?场景")
        self.assertIn("纯色背景", at_500)

    def test_all_five_h3_modes_are_written_verbatim(self):
        for mode in ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"):
            with self.subTest(mode=mode):
                task, _, _ = self._build(499, mode=mode)
                self.assertIn(f"[GMC_H3_MODE={mode}]", task)


class HighCoinTaskTests(unittest.TestCase):
    def _build(self, price: int, *, duration: float = 5.0):
        return build_high_coin_task(
            gift_name="机械莲花",
            gift_price=price,
            creative_brief="金属花瓣逐层展开",
            reference_mode="T2VA",
            target_duration=duration,
            aspect_ratio="1:1",
            shot_structure="双镜头",
            sound_design="",
            extra_constraints="",
        )

    def test_accepts_inclusive_1000_to_3000_boundary(self):
        for price in (1000, 3000):
            with self.subTest(price=price):
                task, frames, actual = self._build(price)
                self.assertIn(f"礼物价格：{price} 抖币", task)
                self.assertEqual(frames / 24, actual)
                self.assertEqual(0, (frames - 5) % 17)

    def test_rejects_high_price_out_of_range(self):
        for price in (999, 3001):
            with self.subTest(price=price), self.assertRaisesRegex(GiftMasterError, "1000.*3000"):
                self._build(price)

    def test_preserves_legacy_high_tier_alignment(self):
        task, frames, duration = self._build(1800, duration=4.0)
        self.assertEqual(107, frames)
        self.assertAlmostEqual(107 / 24, duration)
        self.assertIn("[GMC_H3_DURATION=4.458333]", task)


if __name__ == "__main__":
    unittest.main()
