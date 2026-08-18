from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from giftmaster.errors import SkillError
from giftmaster.skills import discover_skills, load_skill, route_skill
from giftmaster.tasks import build_low_coin_task


class SkillTests(unittest.TestCase):
    def test_builtin_references_are_deterministic_and_evaluation_free(self):
        package = load_skill("h3-low-coin-gift-director", "auto", "Ref2VA")
        names = [name for name, _content in package.references]
        self.assertEqual(["references/price-profile.json", "references/format.md"], names)
        self.assertFalse(any("evaluation" in name.lower() for name in names))

    def test_task_marker_routes_without_guessing(self):
        task, _frames, _seconds = build_low_coin_task("纸鹤", reference_mode="T2VA")
        self.assertEqual("h3-low-coin-gift-director", route_skill(task, "auto"))

    def test_reference_path_traversal_is_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            skill = root / "unsafe-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: unsafe-skill\ndescription: test\n---\n", encoding="utf-8")
            (root / "outside.md").write_text("outside", encoding="utf-8")
            manifest = {
                "id": "unsafe-skill",
                "display_name": "unsafe",
                "profile": "GENERIC",
                "skill_file": "SKILL.md",
                "runtime_references": ["../outside.md"],
            }
            (skill / "giftmaster.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(SkillError, "越出"):
                load_skill("unsafe-skill", roots=[root])

    def test_duplicate_skill_ids_are_rejected(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            for base in (Path(first), Path(second)):
                skill = base / "same-id"
                skill.mkdir()
                (skill / "SKILL.md").write_text("ok", encoding="utf-8")
                (skill / "giftmaster.json").write_text('{"id":"same-id"}', encoding="utf-8")
            with self.assertRaisesRegex(SkillError, "重复"):
                discover_skills([Path(first), Path(second)])


if __name__ == "__main__":
    unittest.main()
