"""
Skills del agente: guías de procedimiento en archivos SKILL.md que se cargan bajo demanda.

Cada skill vive en `skills/<nombre>/SKILL.md` con un frontmatter (`name`, `description`) y las
instrucciones en el cuerpo. Al arrancar el prompt solo recibe el catálogo (nombre y descripción);
el cuerpo entra al contexto cuando el agente llama a `load_skill_tool`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from langchain_core.tools import tool

SKILLS_DIR = Path(__file__).parent
SKILL_FILE = "SKILL.md"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


def _parse(path: Path) -> Skill:
    """Separa el frontmatter (clave: valor entre líneas '---') del cuerpo y valida los campos."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"{path}: falta el frontmatter '---'.")
    meta = {}
    for line in parts[1].strip().splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    name, description = meta.get("name"), meta.get("description")
    if not name or not description:
        raise ValueError(f"{path}: el frontmatter necesita 'name' y 'description'.")
    if name != path.parent.name:
        raise ValueError(f"{path}: 'name' ({name}) debe coincidir con la carpeta ({path.parent.name}).")
    if "{" in description or "}" in description:
        raise ValueError(f"{path}: la descripción no puede llevar llaves (entra al template del prompt).")
    return Skill(name=name, description=description, body=parts[2].strip())


def discover_skills(skills_dir: Path = SKILLS_DIR) -> Dict[str, Skill]:
    """Skills disponibles por nombre, leídas de las subcarpetas que tienen SKILL.md."""
    skills = (_parse(p) for p in sorted(skills_dir.glob(f"*/{SKILL_FILE}")))
    return {s.name: s for s in skills}


def skills_catalog(skills: Dict[str, Skill]) -> str:
    """Una línea 'nombre: descripción' por skill, para el system prompt."""
    return "\n".join(f"- {s.name}: {s.description}" for s in skills.values())


SKILLS = discover_skills()


@tool
def load_skill_tool(name: str) -> str:
    """
    Carga las instrucciones completas de una skill del catálogo de <skills>.
    Parámetros:
    - name: Nombre exacto de la skill, tal como figura en el catálogo.
    """
    skill = SKILLS.get(name)
    if skill is None:
        return f"No existe la skill '{name}'. Skills disponibles: {', '.join(SKILLS)}."
    return skill.body


__all__ = ["SKILLS", "Skill", "discover_skills", "load_skill_tool", "skills_catalog"]
