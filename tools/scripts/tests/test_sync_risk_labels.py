import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_SCRIPTS_DIR = REPO_ROOT / "tools" / "scripts"
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))


def load_module(relative_path: str, module_name: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


sync_risk_labels = load_module(
    "tools/scripts/sync_risk_labels.py",
    "sync_risk_labels_test",
)


class SyncRiskLabelsTests(unittest.TestCase):
    def test_choose_synced_risk_promotes_git_mutation_to_critical(self):
        content = """---
name: commit
description: commit changes safely
risk: unknown
source: community
---

Use `git commit` and `git push` once the branch is ready.
"""
        metadata = {"name": "commit", "description": "commit changes safely", "risk": "unknown"}

        decision = sync_risk_labels.choose_synced_risk(content, metadata)

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision[0], "critical")
        self.assertIn("git mutation", decision[1])

    def test_choose_synced_risk_promotes_read_only_skill_to_safe(self):
        content = """---
name: seo-fundamentals
description: Learn the core principles of SEO.
risk: unknown
source: community
---

## Overview

Review search quality signals and analyze page structure.
"""
        metadata = {"name": "seo-fundamentals", "description": "Learn the core principles of SEO.", "risk": "unknown"}

        decision = sync_risk_labels.choose_synced_risk(content, metadata)

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision[0], "safe")

    def test_choose_synced_risk_keeps_unknown_when_safe_text_mentions_install(self):
        content = """---
name: package-setup
description: Explain how to inspect package setup.
risk: unknown
source: community
---

Use this skill to analyze package setup and install dependencies if needed.
"""
        metadata = {"name": "package-setup", "description": "Explain how to inspect package setup.", "risk": "unknown"}

        decision = sync_risk_labels.choose_synced_risk(content, metadata)

        self.assertIsNone(decision)

    def test_choose_synced_risk_requires_explicit_disclaimer_for_offensive(self):
        content = """---
name: pentest-checklist
description: penetration testing checklist
risk: unknown
source: community
---

Plan a penetration testing engagement and define red team scope.
"""
        metadata = {"name": "pentest-checklist", "description": "penetration testing checklist", "risk": "unknown"}

        decision = sync_risk_labels.choose_synced_risk(content, metadata)

        self.assertIsNone(decision)

    def test_update_skill_file_rewrites_frontmatter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_path = Path(temp_dir) / "SKILL.md"
            skill_path.write_text(
                """---
name: commit
description: commit changes safely
risk: unknown
source: community
---

Use `git commit` before `git push`.
""",
                encoding="utf-8",
            )

            changed, new_risk, reasons = sync_risk_labels.update_skill_file(skill_path)

            self.assertTrue(changed)
            self.assertEqual(new_risk, "critical")
            self.assertIn("git mutation", reasons)
            updated = skill_path.read_text(encoding="utf-8")
            self.assertIn("risk: critical", updated)
            self.assertNotIn("risk: unknown", updated)


if __name__ == "__main__":
    unittest.main()
