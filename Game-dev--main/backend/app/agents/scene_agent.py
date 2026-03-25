"""SceneAgent — generates Godot 4.x .tscn scene files.

The agent asks the AI provider for a JSON *scene specification* that describes
the node tree, external resources, and collision shapes for a single game
entity.  It then renders that spec through a Jinja2 template to produce a
valid Godot text-scene (.tscn) string.

The returned string is ready to be uploaded to S3 by the orchestrator; this
agent does NOT touch the filesystem or S3 directly.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.agents.base_agent import BaseAgent

_TEMPLATE_DIR = str(Path(__file__).resolve().parents[1] / "templates" / "scene_templates")

_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape([]),
)


def _safe_filename(name: str) -> str:
    """Convert entity name to a safe lowercase filename slug."""
    slug = name.lower().replace(" ", "_").replace("-", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "entity"


def _safe_node_name(name: str) -> str:
    """Convert entity name to a valid Godot node name (PascalCase, no special chars)."""
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", name)
    return cleaned.replace(" ", "") or "Entity"


_SYSTEM_PROMPT = """You are a Godot 4.x scene architect.
Your only job is to output a single valid JSON object describing a Godot scene.
Do not include markdown code fences or any text outside the JSON object.

IMPORTANT: node_name must be PascalCase with NO special characters (letters/numbers only).
script_path and texture_path must use lowercase_snake_case filenames with no special chars.

The JSON must follow this exact schema:
{
  "node_type": "<Root node type: CharacterBody2D | Area2D | StaticBody2D | RigidBody2D | Node2D>",
  "node_name": "<PascalCase root node name, e.g. Player, EnemyShip, ScoreDisplay>",
  "script_path": "<res://scripts/snake_case_name.gd or null>",
  "properties": {
    "<property_name>": "<gdscript literal value as a string>"
  },
  "children": [
    {
      "name": "<PascalCase node name>",
      "type": "<Godot node type>",
      "parent": "<parent path, use '.' for root children>",
      "texture_path": "<res://assets/snake_case_name.png or null>",
      "properties": {}
    }
  ],
  "collision_shapes": [
    {
      "type": "<RectangleShape2D | CircleShape2D | CapsuleShape2D>",
      "parent_node": "<name of the CollisionShape2D child this attaches to>",
      "size": [<width>, <height>],
      "radius": <number>
    }
  ]
}

Rules:
- Use null (JSON null) for optional string fields when not applicable.
- "properties" values must be valid GDScript literals as strings.
- Include a CollisionShape2D child for every physics body (CharacterBody2D, StaticBody2D, RigidBody2D).
- Area2D nodes need a CollisionShape2D child too (for detection).
- Node2D and CanvasLayer do NOT need collision shapes.
- Return ONLY the JSON object — nothing else.
"""


class SceneAgent(BaseAgent):
    """Generates a Godot 4.x .tscn file content string for one game entity."""

    temperature: float = 0.3

    async def run(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> str:
        """Generates a Godot 4.x .tscn file content string for one game entity."""
        prompt = self._create_prompt(entity, design_doc)
        try:
            raw = await self.generate(prompt)
            spec = self.extract_json(raw)
            if not spec or "node_type" not in spec:
                spec = self._fallback_spec(entity)
        except Exception:
            spec = self._fallback_spec(entity)

        # Sanitize any AI-generated paths
        spec = self._sanitize_spec(spec, entity)
        return self._render_tscn(entity, spec)

    def _create_prompt(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> str:
        name = entity.get("name", "Entity")
        etype = entity.get("type", "character")
        game_type = design_doc.get("game_type", "arcade")
        mechanics = ", ".join(design_doc.get("mechanics", []))
        fname = _safe_filename(name)
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Entity name: {name}\n"
            f"Entity type: {etype}\n"
            f"Game type: {game_type}\n"
            f"Game mechanics: {mechanics or 'standard'}\n"
            f"Use script_path: res://scripts/{fname}.gd\n"
            f"Use texture_path: res://assets/{fname}.png\n\n"
            f"Generate the Godot scene specification for {name}."
        )

    def _sanitize_spec(self, spec: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
        """Ensure all resource paths in spec use safe filenames."""
        name = entity.get("name", "Entity")
        fname = _safe_filename(name)

        # Fix script path
        sp = spec.get("script_path")
        if sp and isinstance(sp, str):
            spec["script_path"] = f"res://scripts/{fname}.gd"

        # Fix node name
        spec["node_name"] = _safe_node_name(spec.get("node_name", name))

        # Fix children paths
        for child in spec.get("children", []):
            tp = child.get("texture_path")
            if tp and isinstance(tp, str) and tp != "null":
                child["texture_path"] = f"res://assets/{fname}.png"
            child["name"] = re.sub(r"[^a-zA-Z0-9]", "", child.get("name", "Node")) or "Node"

        return spec

    def _fallback_spec(self, entity: dict[str, Any]) -> dict[str, Any]:
        name = entity.get("name", "Entity")
        pascal = _safe_node_name(name)
        fname = _safe_filename(name)
        etype = entity.get("type", "character").lower()

        # Choose node type based on entity type
        # Background must be checked before ground (substring collision)
        if "background" in name.lower() or "background" in etype or any(k in etype for k in ("scenery", "sky")):
            node_type = "Node2D"
        elif any(k in etype for k in ("collect", "trigger", "projectile")):
            node_type = "Area2D"
        elif any(k in etype for k in ("obstacle", "environment")) or any(k in name.lower() for k in ("ground", "wall", "platform")):
            node_type = "StaticBody2D"
        elif any(k in etype for k in ("ui", "display")) or any(k in name.lower() for k in ("score", "hud", "game over", "health")):
            node_type = "Node2D"
        else:
            node_type = "CharacterBody2D"

        children = [
            {
                "name": "Sprite2D",
                "type": "Sprite2D",
                "parent": ".",
                "texture_path": f"res://assets/{fname}.png",
                "properties": {},
            },
        ]

        collision_shapes = []
        # Only add collision for physics/area nodes
        if node_type in ("CharacterBody2D", "StaticBody2D", "RigidBody2D", "Area2D"):
            children.append({
                "name": "CollisionShape2D",
                "type": "CollisionShape2D",
                "parent": ".",
                "texture_path": None,
                "properties": {},
            })
            collision_shapes.append({
                "type": "RectangleShape2D",
                "parent_node": "CollisionShape2D",
                "size": [32, 32],
                "radius": 0,
            })

        return {
            "node_type": node_type,
            "node_name": pascal,
            "script_path": f"res://scripts/{fname}.gd",
            "properties": {},
            "children": children,
            "collision_shapes": collision_shapes,
        }

    def _render_tscn(self, entity: dict[str, Any], spec: dict[str, Any]) -> str:
        uid = uuid.uuid4().hex[:12]
        node_name = spec.get("node_name", _safe_node_name(entity.get("name", "Entity")))
        node_type = spec.get("node_type", "Node2D")
        script_path = spec.get("script_path")
        properties = spec.get("properties", {})
        children = spec.get("children", [])
        collision_shapes = spec.get("collision_shapes", [])

        ext_resources = []
        sub_resources = []
        script_id = None

        # Script as ext_resource
        if script_path:
            script_id = f"Script_{uid}_1"
            ext_resources.append({"type": "Script", "path": script_path, "id": script_id})

        # Textures as ext_resources
        texture_id_map: dict[str, str] = {}
        for i, child in enumerate(children):
            tex = child.get("texture_path")
            if tex and tex != "null" and tex not in texture_id_map:
                res_id = f"Texture_{uid}_{i}"
                texture_id_map[tex] = res_id
                ext_resources.append({"type": "Texture2D", "path": tex, "id": res_id})

        # Collision shapes as sub_resources
        shape_id_map: dict[str, str] = {}
        for i, cs in enumerate(collision_shapes):
            sub_id = f"Shape_{uid}_{i}"
            shape_id_map[cs.get("parent_node", "")] = sub_id
            sub = {"type": cs.get("type", "RectangleShape2D"), "id": sub_id}
            if cs.get("size"):
                sub["size"] = cs["size"]
            if cs.get("radius"):
                sub["radius"] = cs["radius"]
            sub_resources.append(sub)

        # Build child node data for template
        rendered_children = []
        for child in children:
            tex = child.get("texture_path")
            cname = child.get("name", "Node")
            rendered_children.append({
                "name": cname,
                "type": child.get("type", "Node2D"),
                "parent": child.get("parent", "."),
                "texture_id": texture_id_map.get(tex) if tex else None,
                "shape_id": shape_id_map.get(cname),
                "properties": child.get("properties", {}),
            })

        load_steps = 1 + len(ext_resources) + len(sub_resources)

        root = {
            "name": node_name,
            "type": node_type,
            "script_id": script_id,
            "properties": properties,
            "children": rendered_children,
        }

        try:
            template = _jinja_env.get_template("node.tscn.j2")
            return template.render(
                load_steps=load_steps,
                ext_resources=ext_resources,
                sub_resources=sub_resources,
                root=root,
            )
        except Exception:
            # Minimal fallback tscn
            return f'[gd_scene format=3]\n[node name="{node_name}" type="{node_type}"]\n'


scene_agent = SceneAgent()
