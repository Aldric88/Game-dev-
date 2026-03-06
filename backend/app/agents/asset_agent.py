"""AssetAgent — procedural sprite and asset generation for Godot 4.x projects.

The agent:
1. Asks the AI provider for a JSON *asset specification* (colors, shape, animations).
2. Uses PIL/Pillow to synthesise the actual PNG images from that spec.
3. Returns base64-encoded PNG strings — upload to S3 is handled by the orchestrator.

No filesystem or S3 access happens here.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

from PIL import Image, ImageDraw

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_COLOR_PALETTE: dict[str, str] = {
    "blue": "#4A90E2",
    "red": "#E74C3C",
    "yellow": "#F1C40F",
    "gray": "#7F8C8D",
    "white": "#ECF0F1",
    "purple": "#8E44AD",
    "green": "#27AE60",
    "orange": "#E67E22",
    "dark": "#5D6D7E",
    "light_green": "#2ECC71",
}

_DEFAULT_COLOR = "#95A5A6"
_SPRITE_SIZE = (32, 32)
_TILE_SIZE = (16, 16)
_BG_SIZE = (256, 256)

_SYSTEM_PROMPT = """You are a game asset designer for a 2D Godot game.
Your only job is to output a single valid JSON object describing sprite assets.
Do not include markdown code fences or any text outside the JSON object.

The JSON must follow this exact schema:
{
  "sprite": {
    "width": <integer between 16 and 128>,
    "height": <integer between 16 and 128>,
    "shape": "<rectangle | circle | triangle>",
    "color_scheme": ["<primary hex color e.g. #4A90E2>", "<accent hex color e.g. #FFFFFF>"]
  },
  "animations": [
    {
      "name": "<e.g. idle | walk | jump | attack | collect>",
      "frames": <integer 1-8>,
      "frame_duration": <float seconds per frame, e.g. 0.1>
    }
  ],
  "sound_effects": [
    {
      "event": "<e.g. jump | collect | hit | death>",
      "type": "<beep | noise | tone>",
      "pitch": <integer Hz, e.g. 440>,
      "duration": <float seconds, e.g. 0.2>
    }
  ]
}

Rules:
- "shape" must be exactly one of: rectangle, circle, triangle.
- "color_scheme" must have exactly 2 valid CSS hex colors.
- "animations" must have 1-4 entries suited to the entity type.
- "sound_effects" may be an empty array [].
- Return ONLY the JSON object — nothing else.
"""


class AssetAgent(BaseAgent):
    """Generates procedural sprite images for Godot 4.x game entities.

    The AI provider supplies the visual specification (colors, shape, animations).
    PIL draws the actual pixels. The orchestrator handles S3 upload.
    """

    temperature: float = 0.5
    color_palette: dict[str, str] = _COLOR_PALETTE
    default_sprite_size: tuple[int, int] = _SPRITE_SIZE

    async def run(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> dict[str, Any]:
        """Generates procedural sprite images for Godot 4.x game entities."""
        prompt = self._create_prompt(entity, design_doc)
        try:
            raw = await self.generate(prompt)
            spec = self.extract_json(raw)
            if not spec:
                spec = self._fallback_spec(entity)
        except Exception:
            spec = self._fallback_spec(entity)

        return self._generate_sprite(entity, spec)

    async def generate_tileset(self, design_doc: dict[str, Any]) -> str:
        """Generate a tileset PNG (base64) for the game world."""
        size = (128, 16)
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        colors = ["#27AE60", "#7F8C8D", "#E67E22", "#4A90E2",
                  "#2ECC71", "#95A5A6", "#F1C40F", "#8E44AD"]
        tile_w = size[0] // len(colors)
        for i, color in enumerate(colors):
            rgba = self._hex_to_rgba(color)
            draw.rectangle([i * tile_w, 0, (i + 1) * tile_w - 1, size[1] - 1], fill=rgba)

        return self._img_to_asset(img)

    async def generate_background(self, design_doc: dict[str, Any]) -> str:
        """Generate a background PNG (base64) for the game world."""
        img = Image.new("RGBA", _BG_SIZE, (17, 17, 34, 255))
        draw = ImageDraw.Draw(img)

        # Simple gradient-like background with horizon
        for y in range(_BG_SIZE[1]):
            ratio = y / _BG_SIZE[1]
            r = int(17 + ratio * 30)
            g = int(17 + ratio * 20)
            b = int(34 + ratio * 50)
            draw.line([(0, y), (_BG_SIZE[0], y)], fill=(r, g, b, 255))

        # Ground line
        draw.rectangle([0, _BG_SIZE[1] - 20, _BG_SIZE[0], _BG_SIZE[1]], fill=(39, 174, 96, 255))

        return self._img_to_asset(img)

    def _create_prompt(self, entity: dict[str, Any], design_doc: dict[str, Any]) -> str:
        name = entity.get("name", "Entity")
        etype = entity.get("type", "character")
        game_type = design_doc.get("game_type", "arcade")
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Entity name: {name}\n"
            f"Entity type: {etype}\n"
            f"Game type: {game_type}\n"
            f"Generate asset specification for this entity."
        )

    def _fallback_spec(self, entity: dict[str, Any]) -> dict[str, Any]:
        return {
            "sprite": {
                "width": 32,
                "height": 32,
                "shape": "rectangle",
                "color_scheme": ["#4A90E2", "#ECF0F1"],
            },
            "animations": [{"name": "idle", "frames": 1, "frame_duration": 0.1}],
            "sound_effects": [],
        }

    def _generate_sprite(self, entity: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        sprite_spec = spec.get("sprite", {})
        w = max(16, min(128, int(sprite_spec.get("width", 32))))
        h = max(16, min(128, int(sprite_spec.get("height", 32))))
        shape = sprite_spec.get("shape", "rectangle")
        colors = sprite_spec.get("color_scheme", ["#4A90E2", "#ECF0F1"])
        primary = colors[0] if colors else "#4A90E2"
        accent = colors[1] if len(colors) > 1 else "#ECF0F1"

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        primary_rgba = self._hex_to_rgba(primary)
        accent_rgba = self._hex_to_rgba(accent)

        if shape == "circle":
            draw.ellipse([2, 2, w - 3, h - 3], fill=primary_rgba, outline=accent_rgba, width=2)
            self._add_eyes(draw, w, h, accent_rgba)
        elif shape == "triangle":
            pts = [(w // 2, 2), (2, h - 3), (w - 3, h - 3)]
            draw.polygon(pts, fill=primary_rgba, outline=accent_rgba)
        else:
            draw.rectangle([2, 2, w - 3, h - 3], fill=primary_rgba, outline=accent_rgba, width=2)
            entity_name = entity.get("name", "").lower()
            if any(k in entity_name for k in ("coin", "gold", "collect")):
                self._add_coin_shine(draw, w, h, accent_rgba)
            else:
                self._add_eyes(draw, w, h, accent_rgba)

        # Darker bottom edge for depth
        dark = self._darken(primary_rgba)
        draw.line([(2, h - 3), (w - 3, h - 3)], fill=dark, width=2)

        return {
            "spec": spec,
            "png_b64": self._img_to_asset(img),
            "width": w,
            "height": h,
        }

    def _add_eyes(self, draw: ImageDraw.Draw, w: int, h: int, color: tuple) -> None:
        ex = w // 4
        ey = h // 3
        es = max(2, w // 8)
        draw.ellipse([ex - es, ey - es, ex + es, ey + es], fill=color)
        draw.ellipse([w - ex - es, ey - es, w - ex + es, ey + es], fill=color)

    def _add_coin_shine(self, draw: ImageDraw.Draw, w: int, h: int, color: tuple) -> None:
        draw.ellipse([w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill=color)

    @staticmethod
    def _img_to_asset(img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (r, g, b, 255)

    @staticmethod
    def _darken(rgba: tuple[int, int, int, int], factor: float = 0.7) -> tuple[int, int, int, int]:
        r, g, b, a = rgba
        return (int(r * factor), int(g * factor), int(b * factor), a)


asset_agent = AssetAgent()
