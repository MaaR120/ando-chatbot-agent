"""
Tests for the on-demand skills: SKILL.md discovery, catalog in the prompt and load_skill_tool.
"""
import tempfile
import unittest
from pathlib import Path

from app.agent.prompts import ANDO_AGENT_SYSTEM_PROMPT
from app.agent.skills import SKILLS, discover_skills, load_skill_tool, skills_catalog
from app.agent.tools import build_agent_tools


class TestSkillDiscovery(unittest.TestCase):
    def write_skill(self, root: Path, folder: str, content: str):
        (root / folder).mkdir()
        (root / folder / "SKILL.md").write_text(content, encoding="utf-8")

    def test_pdf_skill_is_discovered(self):
        self.assertIn("armar-itinerario", SKILLS)
        self.assertTrue(SKILLS["armar-itinerario"].description)
        self.assertIn("generar_pdf", SKILLS["armar-itinerario"].body)

    def test_parses_frontmatter_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "demo", "---\nname: demo\ndescription: Una demo\n---\n\n# Cuerpo\n")
            skill = discover_skills(root)["demo"]
        self.assertEqual((skill.name, skill.description, skill.body), ("demo", "Una demo", "# Cuerpo"))

    def test_rejects_name_different_from_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "demo", "---\nname: otra\ndescription: x\n---\ncuerpo")
            with self.assertRaises(ValueError):
                discover_skills(root)

    def test_rejects_missing_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "demo", "# Sin frontmatter")
            with self.assertRaises(ValueError):
                discover_skills(root)

    def test_rejects_braces_in_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill(root, "demo", "---\nname: demo\ndescription: usa {sesion}\n---\ncuerpo")
            with self.assertRaises(ValueError):
                discover_skills(root)


class TestLoadSkillTool(unittest.TestCase):
    def test_returns_the_body(self):
        self.assertEqual(load_skill_tool.invoke({"name": "armar-itinerario"}), SKILLS["armar-itinerario"].body)

    def test_unknown_name_lists_available_skills(self):
        result = load_skill_tool.invoke({"name": "../../.env"})
        self.assertIn("No existe", result)
        self.assertIn("armar-itinerario", result)

    def test_tool_is_available_without_session(self):
        names = [t.name for t in build_agent_tools(None)]
        self.assertIn("load_skill_tool", names)


class TestPromptCatalog(unittest.TestCase):
    def test_prompt_lists_name_and_description_but_not_the_body(self):
        self.assertIn(skills_catalog(SKILLS), ANDO_AGENT_SYSTEM_PROMPT)
        self.assertNotIn("Reglas de redacción", ANDO_AGENT_SYSTEM_PROMPT)
        self.assertNotIn("__CATALOGO_DE_SKILLS__", ANDO_AGENT_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
