"""AI orchestration — async multi-agent pipeline for game generation."""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.asset_agent import asset_agent
from app.agents.scene_agent import scene_agent
from app.agents.script_agent import _fallback_for as _fallback_script, script_agent
from app.services.ai_providers import (
    ProviderUsage,
    provider_manager,
    start_token_accumulation,
    stop_token_accumulation,
)
from app.services.s3_storage import s3_storage
from app.services.game_inference import (
    _normalize_entity,
    _infer_game_type as infer_game_type,
    _infer_entities as infer_entities,
    _fallback_design as fallback_design,
    _fallback_code as fallback_code,
    get_html_fallback_game,
    _extract_json_object as extract_json_object,
)
from app.services.godot_file_generators import (
    _generate_project_config,
    _generate_main_scene,
    _generate_icon_svg,
    _generate_readme,
)
from app.services.github_service import search_similar_repos
from app.services.code_extractor import fetch_reference_code
from app.schemas.mapl import MemoryAction, MemoryState, Outcome
from app.services.mapl_service import mapl_service

logger = logging.getLogger(__name__)


@dataclass
class GodotGenerateResult:
    design_doc: dict[str, Any] = field(default_factory=dict)
    file_urls: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    status: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class OrchestratorResult:
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    usage: ProviderUsage = field(default_factory=ProviderUsage)


async def _emit(realtime: Any, project_id: str, event: str, payload: Any = None) -> None:
    """Broadcast a WebSocket event; silently no-ops if realtime is None."""
    if realtime is None:
        return
    try:
        await realtime.broadcast(project_id, event, payload)
    except Exception:
        pass


class AIOrchestrator:
    def _format_history(self, history: list[dict]) -> str:
        if not history:
            return ""
        lines = ["\nPREVIOUS CONVERSATION HISTORY:"]
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role.upper()}: {content}")
        lines.append("END HISTORY\n")
        return "\n".join(lines)

    async def generate_design(
        self,
        prompt: str,
        history: list[dict] | None = None,
        storage: Any = None,
        user_id: str = "",
    ) -> OrchestratorResult:
        system = (
            "You are an expert game design architect who creates DETAILED, SPECIFIC game designs. "
            "Analyze the request and return a COMPLETE Game Design Document as strict JSON.\n"
            "Do NOT include markdown formatting like ```json ... ``` or any text outside the JSON.\n\n"
            "IMPORTANT RULES:\n"
            "- Generate AT LEAST 5-8 entities for any game. Every game needs enemies, obstacles, "
            "collectibles, UI elements, and environmental objects — not just a player.\n"
            "- Mechanics MUST be specific to the game type (e.g., racing needs steering/drifting/boost, "
            "NOT jumping/gravity).\n"
            "- Entity names should be descriptive (e.g., 'Player Car', 'AI Opponent', 'Speed Boost', "
            "'Finish Line' for racing — NOT generic 'Player', 'Enemy').\n"
            "- Include visual/theme details in the summary.\n\n"
            "The JSON must strictly follow this schema:\n"
            "{\n"
            '  "summary": "Detailed overview including theme, art style, and gameplay feel",\n'
            '  "game_type": "One of: platformer, shooter, rpg, puzzle, arcade, racing, flappy, '
            'snake, space_shooter, fighting, survival, topdown, tower_defense",\n'
            '  "mechanics": ["List of 5-8 SPECIFIC core mechanics relevant to this game type"],\n'
            '  "entities": [\n'
            '    {"name": "Descriptive Name", "type": "character|enemy|collectible|obstacle|ui|environment", '
            '"behaviors": ["specific_behavior_1", "specific_behavior_2"]}\n'
            "  ],\n"
            '  "win_conditions": ["List of 2-3 win/lose conditions"],\n'
            '  "visual_style": {"theme": "e.g. neon, retro, pixel, minimalist", '
            '"primary_colors": ["#hex1", "#hex2", "#hex3"], '
            '"background": "#hex_bg_color"},\n'
            '  "technical_requirements": {"framework": "canvas", "width": 960, "height": 640}\n'
            "}"
        )
        history_text = self._format_history(history or [])
        user_prompt = f"{history_text}\nCURRENT REQUEST: {prompt}"

        # ── MAPL: Augment prompt with past experiences (Eq. 4) ────────────
        mapl_memories = []
        if storage is not None:
            try:
                current_state = MemoryState(prompt=prompt)
                user_prompt, mapl_memories = await mapl_service.build_augmented_prompt(
                    current_state=current_state,
                    base_prompt=user_prompt,
                    storage=storage,
                    user_id=user_id,
                )
                if mapl_memories:
                    logger.info(
                        "MAPL: Augmented design prompt with %d past experiences",
                        len(mapl_memories),
                    )
            except Exception as mapl_err:
                logger.warning("MAPL augmentation skipped: %s", mapl_err)

        full_prompt = f"{system}\n{user_prompt}"

        try:
            result = await provider_manager.generate(full_prompt, temperature=0.7)
            design = extract_json_object(result.text)
            if not design:
                design = fallback_design(prompt)
            summary = design.get("summary", "Generated game design.")
            return OrchestratorResult(summary=summary, payload=design, usage=result.usage)
        except Exception:
            design = fallback_design(prompt)
            return OrchestratorResult(
                summary=design["summary"],
                payload=design,
                usage=ProviderUsage(),
            )

    async def generate_code(
        self,
        prompt: str,
        design_doc: dict[str, Any] | None = None,
        history: list[dict] | None = None,
        realtime: Any = None,
        project_id: str | None = None,
    ) -> OrchestratorResult:
        """Full multi-agent pipeline: Design → Assets/Scripts/Scenes → HTML5 game + Godot files.

        All agents call Gemini via the shared ProviderManager. The final output
        includes a playable index.html for browser preview AND Godot 4.x project
        files (.gd scripts, .tscn scenes, project.godot) for engine export.
        """
        total_usage = ProviderUsage(provider="gemini", model="multi-agent-pipeline")
        errors: list[str] = []

        # ── Phase 1: Design Agent ── Generate game design doc via Gemini
        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "design", "status": "running", "message": "Designing game architecture..."})

        if not design_doc or not design_doc.get("entities"):
            try:
                design_result = await self.generate_design(prompt, history)
                design_doc = design_result.payload
                if design_result.usage.total_tokens:
                    total_usage.total_tokens = (total_usage.total_tokens or 0) + design_result.usage.total_tokens
            except Exception as e:
                errors.append(f"Design agent error: {e}")
                design_doc = fallback_design(prompt)

        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "design", "status": "complete",
                         "message": f"Game type: {design_doc.get('game_type', 'arcade')} with {len(design_doc.get('entities', []))} entities"})

        # Normalize entities
        entities_raw = design_doc.get("entities", ["Player"])
        entities = [_normalize_entity(e) for e in entities_raw]
        if not any(e["type"] in ("character", "player") for e in entities):
            entities.insert(0, _normalize_entity("Player"))

        # ── GitHub Reference Code Fetch (best-effort, non-blocking) ──────────
        github_reference_code = ""
        try:
            game_type_for_search = design_doc.get("game_type", "arcade")
            framework_for_search = design_doc.get(
                "technical_requirements", {}
            ).get("framework", "phaser")
            repos = await asyncio.wait_for(
                search_similar_repos(game_type_for_search, framework_for_search),
                timeout=7.0,
            )
            if repos:
                github_reference_code = await asyncio.wait_for(
                    fetch_reference_code(repos),
                    timeout=10.0,
                )
        except (asyncio.TimeoutError, Exception) as _gh_err:
            logger.info("GitHub enrichment skipped: %s", _gh_err)

        # ── Phase 2: Parallel Agent Execution — Scripts, Scenes, Assets via Gemini
        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scripts", "status": "running",
                         "message": f"Generating GDScript for {len(entities)} entities..."})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scenes", "status": "running",
                         "message": f"Building Godot scenes..."})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assets", "status": "running",
                         "message": f"Creating sprite assets..."})

        script_tasks = [script_agent.run(e, design_doc) for e in entities]
        scene_tasks = [scene_agent.run(e, design_doc) for e in entities]
        asset_tasks = [asset_agent.run(e, design_doc) for e in entities]

        # Accumulate tokens from all concurrent agent calls via the ContextVar
        # accumulator — coroutines (not tasks) share the same context in gather().
        agent_tokens, ctx_token = start_token_accumulation()
        try:
            all_results = await asyncio.gather(
                *script_tasks, *scene_tasks, *asset_tasks,
                return_exceptions=True,
            )
        finally:
            stop_token_accumulation(ctx_token)

        if agent_tokens:
            total_usage.total_tokens = (total_usage.total_tokens or 0) + sum(agent_tokens)

        n = len(entities)
        script_map: dict[str, str] = {}
        scene_map: dict[str, str] = {}
        asset_map: dict[str, dict] = {}

        for i, entity in enumerate(entities):
            ename = entity["name"].lower().replace(" ", "_")
            # Scripts
            res = all_results[i]
            if isinstance(res, Exception):
                errors.append(f"Script agent failed for {ename}: {res}")
                script_map[ename] = _fallback_script(entity)
            else:
                script_map[ename] = res
            # Scenes
            res = all_results[n + i]
            if isinstance(res, Exception):
                errors.append(f"Scene agent failed for {ename}: {res}")
                scene_map[ename] = f'[gd_scene format=3]\n[node name="{ename}" type="Node2D"]\n'
            else:
                scene_map[ename] = res
            # Assets
            res = all_results[2 * n + i]
            if isinstance(res, Exception):
                errors.append(f"Asset agent failed for {ename}: {res}")
                asset_map[ename] = {"spec": {}, "png_b64": None, "width": 32, "height": 32}
            else:
                asset_map[ename] = res

        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scripts", "status": "complete", "message": f"{len(script_map)} scripts generated"})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "scenes", "status": "complete", "message": f"{len(scene_map)} scenes generated"})
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assets", "status": "complete", "message": f"{len(asset_map)} assets generated"})

        # ── Phase 3: Generate comprehensive HTML5 game with full design context
        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assembler", "status": "running", "message": "Building playable HTML5 game..."})

        html_game = await self._generate_rich_html_game(
            prompt, design_doc, entities, script_map, asset_map, history,
            reference_code=github_reference_code,
        )

        if realtime and project_id:
            await _emit(realtime, project_id, "agent_progress",
                        {"agent": "assembler", "status": "complete", "message": "Game assembled successfully"})

        # ── Phase 4: Assemble ALL files — HTML5 preview + Godot project
        game_name = design_doc.get("game_type", "game").title() + " Game"
        files: dict[str, str] = {}

        # HTML5 playable game (browser preview)
        files["index.html"] = html_game

        # Godot project files
        files["project.godot"] = _generate_project_config(game_name)
        files["scenes/main.tscn"] = _generate_main_scene(entities)
        files["icon.svg"] = _generate_icon_svg()
        files["README.md"] = _generate_readme(
            design_doc.get("game_type", "arcade"),
            design_doc.get("mechanics", []),
        )

        for ename, content in script_map.items():
            if isinstance(content, str) and content.strip():
                files[f"scripts/{ename}.gd"] = content
        for ename, content in scene_map.items():
            if isinstance(content, str) and content.strip():
                files[f"scenes/{ename}.tscn"] = content

        summary = (
            f"Generated {design_doc.get('game_type', 'arcade')} game with "
            f"{len(entities)} entities, {len(script_map)} scripts, "
            f"{len(scene_map)} scenes. "
            f"Preview the HTML5 version in-browser or export the Godot 4.x project files."
        )
        if errors:
            summary += f" ({len(errors)} non-fatal warnings during generation)"

        payload = {
            "summary": summary,
            "files": files,
            "entry_point": "index.html",
            "dependencies": [],
            "design_doc": design_doc,
            "godot_stats": {
                "entities": len(entities),
                "scripts": len(script_map),
                "scenes": len(scene_map),
                "assets": len(asset_map),
            },
            "agent_errors": errors,
        }

        return OrchestratorResult(summary=summary, payload=payload, usage=total_usage)

    def _get_game_type_instructions(self, game_type: str, prompt: str) -> str:
        """Return detailed game-type-specific rendering and gameplay instructions."""
        instructions: dict[str, str] = {
            "racing": """RACING GAME SPECIFICS:
- TOP-DOWN VIEW with the track filling most of the canvas.
- Draw a PROPER RACE TRACK — curved roads with lane markings, grass/sand edges, grandstands.
  Use bezier curves or pre-defined path points. NOT a simple rectangle.
- Draw CARS that look like real top-down cars: body shape with rounded front, visible wheels,
  windshield, exhaust trail particles when accelerating.
- Implement REAL DRIFTING physics: when drift key is held, the car slides with reduced traction,
  leaving tire marks on the track. Award drift score.
- AI opponent cars that follow the track with some variation and can overtake.
- SPEEDOMETER as a visual gauge (arc with needle), not just a number.
- Lap counter, position indicator, minimap of the track.
- Checkpoints marked with visible flags or lines.
- Speed boost pads on the track with a glow effect.
- Camera follows the player car smoothly.
- Tire screech sound on drift, engine hum that changes pitch with speed.
- Finish line with checkered flag pattern.""",

            "platformer": """PLATFORMER SPECIFICS:
- SIDE-SCROLLING VIEW with parallax background layers (sky, mountains, trees).
- Draw the PLAYER as an animated character with idle, run, and jump poses (swap sprite frames).
- PLATFORMS should look like ground/stone/wood with textures drawn via patterns, not flat rectangles.
- Enemies should have distinct looks (e.g., slimes with bounce animation, flying bats with wing flaps).
- Coins should ROTATE (draw as ellipse that changes width over time) with sparkle particles.
- Implement wall-jumping, double-jumping, and coyote time for responsive controls.
- Scrolling camera that follows the player with smooth lerp.
- Death animation (player flashes and falls off screen).
- Level progression with increasing difficulty.""",

            "shooter": """SHOOTER SPECIFICS:
- Player ship with engine glow and exhaust particles.
- Enemy ships with distinct silhouettes (small fighters, medium cruisers, large bosses).
- Bullets should have TRAILS (glowing lines behind them).
- EXPLOSIONS with expanding circles, debris particles, and screen flash.
- Power-up drops: shield (bubble around ship), spread shot, rapid fire.
- Boss fights with health bars and attack patterns (bullet hell style).
- Scrolling starfield background with parallax star layers.
- Score multiplier for consecutive hits.""",

            "space_shooter": """SPACE SHOOTER SPECIFICS:
- Vertical or horizontal scrolling space shooter.
- Draw detailed ships with wings, cockpits, and engine glows using canvas paths.
- Animated starfield background with multiple parallax layers and nebula colors.
- Bullet types: laser beams (thin bright lines with glow), missiles (with smoke trail),
  spread shots.
- Asteroids that break into smaller pieces when shot.
- Shield power-ups with visible bubble effect.
- Boss enemies with multiple destructible parts and complex attack patterns.
- Screen-wide special weapon effects.""",

            "flappy": """FLAPPY BIRD SPECIFICS:
- Draw a PROPER BIRD with body, wing (animated flapping), eye, and beak — not a circle.
- Pipes should look like pipes: green gradient with caps, proper 3D-ish shading.
- Scrolling background with sky gradient, clouds, and distant city/trees.
- Ground with grass texture pattern scrolling at different speed.
- Bird should rotate based on velocity (nose up when flapping, nose down when falling).
- Smooth flap animation with wing position changing.
- Score displayed large and centered at top with outlined text.
- Screen flash white briefly on death.
- Increasing difficulty: pipes get closer together or gaps get smaller.""",

            "snake": """SNAKE GAME SPECIFICS:
- Draw the snake with a gradient-colored body, distinct head with eyes and tongue.
- Grid-based movement with smooth interpolation between cells.
- Food items that pulse/glow to attract attention.
- Snake body segments should have rounded corners and slight size variation.
- Trail effect as snake moves.
- Growing animation when eating.
- Wall or border with visible pattern.
- Speed increases as snake grows.
- Different food types worth different points with different colors.""",

            "puzzle": """PUZZLE GAME SPECIFICS:
- Clear, colorful game pieces with distinct shapes AND colors for accessibility.
- Smooth piece movement animations (slide, snap-to-grid).
- Match/clear effects: pieces shatter into colored particles, chain combos flash and shake.
- Score combo multiplier with big animated text ("COMBO x3!").
- Grid lines visible but subtle.
- Preview of next piece/move.
- Timer bar that changes color as time runs out.
- Satisfying clear sounds (ascending tones for combos).""",

            "rpg": """RPG SPECIFICS:
- Top-down view with tile-based movement.
- Character with walking animation (sprite frame cycling per direction).
- Enemies with unique looks and health bars above them.
- Combat: attack animation (slash effect), damage numbers floating up.
- Inventory/health display in a panel.
- NPCs with speech bubbles for dialogue.
- Treasure chests with opening animation.
- Different terrain types (grass, stone, water) drawn with pattern variations.
- XP bar and level-up effect (flash + particle burst).""",

            "fighting": """FIGHTING GAME SPECIFICS:
- Two fighters facing each other with distinct body shapes and colors.
- Draw fighters with proper proportions: head, torso, arms, legs.
- Attack animations: punch (arm extends), kick (leg extends), block (arms crossed).
- Health bars at top of screen with fighter names, round indicator.
- Hit effects: impact flash, hit sparks, knockback.
- Special move with charge-up glow and dramatic effect.
- Arena/stage background with floor and scenery.
- Combo counter for consecutive hits.
- Round-based gameplay (best of 3).""",

            "survival": """SURVIVAL/ROGUELIKE SPECIFICS:
- Top-down view with player in center, enemies approaching from all sides.
- Auto-attack mechanic or simple attack in facing direction.
- Wave counter and increasing enemy count/speed.
- XP orbs that float toward the player with a magnetic effect.
- Level-up screen with weapon/ability choices.
- Player health bar and XP bar at bottom.
- Enemies explode into particles on death.
- Different enemy types with visual distinctions (colors, sizes, shapes).
- Damage numbers floating above enemies.
- Screen gets more intense (redder vignette) as health drops.""",

            "tower_defense": """TOWER DEFENSE SPECIFICS:
- Top-down grid view with clear path for enemies.
- Towers drawn as distinct structures (turrets, magic towers, cannons).
- Enemy path highlighted or visible.
- Projectiles from towers to enemies with trail effects.
- Enemy health bars above them.
- Gold/resource counter for building towers.
- Wave indicator and countdown timer.
- Tower range shown as translucent circle on hover/select.
- Upgrade effects (tower gets bigger/changes color).""",

            "topdown": """TOP-DOWN GAME SPECIFICS:
- 8-directional movement with proper rotation toward movement direction.
- Draw player and enemies as detailed top-down sprites (body, head visible from above).
- Proper top-down environment: walls, floors, doors with shadows.
- Projectiles with trail effects.
- Enemy AI: pathfinding toward player, different attack patterns.
- Minimap in corner showing layout.
- Pickups with floating and glowing animation.""",
        }

        base = instructions.get(game_type, instructions.get("arcade", """ARCADE GAME SPECIFICS:
- Fast-paced, easy to learn, hard to master gameplay.
- Clear player character with proper sprite drawing (not just a rectangle).
- Enemies with distinct visual profiles.
- Collectibles with shine/glow animations.
- Increasing difficulty curve.
- High score tracking.
- Visual juice: screen shake, particles, flashes on every interaction."""))

        return base

    async def _generate_rich_html_game(
        self,
        prompt: str,
        design_doc: dict[str, Any],
        entities: list[dict[str, Any]],
        script_map: dict[str, str],
        asset_map: dict[str, dict],
        history: list[dict] | None = None,
        reference_code: str = "",
    ) -> str:
        """Use Gemini to create a comprehensive HTML5 game informed by all agent outputs."""

        game_type = design_doc.get("game_type", "arcade")

        # Build entity descriptions with their behaviors from GDScript analysis
        entity_descriptions = []
        for entity in entities:
            ename = entity["name"].lower().replace(" ", "_")
            script_code = script_map.get(ename, "")
            asset_data = asset_map.get(ename, {})
            spec = asset_data.get("spec", {}) if isinstance(asset_data, dict) else {}
            sprite_spec = spec.get("sprite", {}) if isinstance(spec, dict) else {}
            colors = sprite_spec.get("color_scheme", ["#4A90E2", "#ECF0F1"])
            shape = sprite_spec.get("shape", "rectangle")

            # Extract key behaviors from GDScript
            behaviors = []
            if "move_and_slide" in script_code:
                behaviors.append("physics-based movement")
            if "JUMP_VELOCITY" in script_code or "jump" in script_code.lower():
                behaviors.append("jumping")
            if "patrol" in script_code.lower() or "_direction" in script_code:
                behaviors.append("patrol AI")
            if "queue_free" in script_code:
                behaviors.append("collectible (disappears on contact)")
            if "gravity" in script_code.lower():
                behaviors.append("affected by gravity")

            entity_descriptions.append(
                f"  - {entity['name']} (type: {entity['type']}): "
                f"shape={shape}, colors={colors}, behaviors=[{', '.join(behaviors)}]"
            )

        entity_text = "\n".join(entity_descriptions)
        mechanics = ", ".join(design_doc.get("mechanics", ["standard"]))
        win_conditions = ", ".join(design_doc.get("win_conditions", ["Score points"]))

        # Visual style from design doc (if available)
        visual_style = design_doc.get("visual_style", {})
        theme = visual_style.get("theme", "modern")
        bg_color = visual_style.get("background", "#0a0a0a")
        primary_colors = visual_style.get("primary_colors", ["#4A90E2", "#E74C3C", "#F1C40F"])

        # Game-type specific rendering and gameplay instructions
        game_type_instructions = self._get_game_type_instructions(game_type, prompt)

        system = f"""You are an ELITE HTML5 game developer who creates POLISHED, VISUALLY IMPRESSIVE,
FULLY PLAYABLE games. You take great pride in making games that look and feel PROFESSIONAL.

== GAME DESIGN (from Design Agent) ==
Game type: {game_type}
Mechanics: {mechanics}
Win conditions: {win_conditions}
Summary: {design_doc.get('summary', 'A fun game')}
Visual theme: {theme}
Background color: {bg_color}
Color palette: {', '.join(primary_colors)}

== ENTITIES (from Script & Asset Agents) ==
{entity_text}

== GAME-TYPE SPECIFIC REQUIREMENTS ==
{game_type_instructions}

== VISUAL QUALITY REQUIREMENTS ==
1. DRAW PROPER SPRITES — NOT just colored rectangles! Use ctx.beginPath(), arcs, lines,
   gradients, and composite shapes to draw recognizable game objects:
   - Cars should look like cars (body, wheels, windshield, spoiler)
   - Characters should have heads, bodies, limbs, and eyes
   - Enemies should look menacing with distinct silhouettes
   - Coins/pickups should shine and animate (rotation, glow)
   - Backgrounds should have depth (parallax, gradient skies, terrain)
2. Use GRADIENTS (ctx.createLinearGradient / ctx.createRadialGradient) for polished visuals.
3. Add SHADOWS (ctx.shadowColor, ctx.shadowBlur) for depth.
4. Implement SMOOTH ANIMATIONS — easing functions, not sudden state changes.
5. Screen shake on impacts, flash effects on damage.
6. Draw proper TRAILS and PARTICLE EFFECTS for movement, explosions, collections.
7. Use GLOW EFFECTS (shadowBlur with bright colors) for power-ups and collectibles.
8. Render a PROPER HUD with styled score, health bars, and progress indicators.
9. Starfield / parallax scrolling backgrounds where appropriate.

== CORE REQUIREMENTS ==
1. Single HTML file with ALL CSS in <style> and ALL JS in <script>.
2. Use HTML5 Canvas for rendering — no DOM-based game objects.
3. COMPLETE game logic: player controls, enemy AI, collision detection, scoring, lives/health,
   game over, restart. The game MUST be fully playable with clear objectives.
4. requestAnimationFrame game loop with proper deltaTime.
5. Keyboard controls: Arrow keys / WASD + Space for action.
6. Font: font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif;
7. -webkit-font-smoothing: antialiased; on body
8. NO external libraries, CDNs, images, or assets. 100% self-contained.
9. Multiple levels or increasing difficulty over time.
10. Start screen with animated title, controls guide, and "Press SPACE to start".
11. Game over screen with final score and restart option.
12. Sound effects using Web Audio API (beeps, tones, noise bursts for different events).
13. Responsive canvas that fills the viewport.
14. At least 3 distinct particle effect types (explosion, trail, sparkle).
15. Smooth camera or viewport management where applicable.

== ORIGINAL USER REQUEST ==
{prompt}
"""

        # Append GitHub reference code if available
        if reference_code.strip():
            system += f"""
== REFERENCE CODE FROM SIMILAR OPEN-SOURCE GAME ==
Study the following code from a real community game project.
Use it to inform game mechanics, collision logic, scoring, and structure.
Do NOT copy it verbatim — adapt and improve the ideas in your own implementation.

{reference_code}

"""

        system += """Return ONLY the complete HTML document starting with <!DOCTYPE html> and ending with </html>.
Do NOT wrap in JSON. Do NOT add markdown fences. Return ONLY the raw HTML.
The game MUST be immediately playable, visually polished, and FUN when loaded in a browser."""

        history_text = self._format_history(history or [])
        full_prompt = f"{system}{history_text}\n\nUSER REQUEST: {prompt}"

        try:
            result = await provider_manager.generate(full_prompt, temperature=0.6)
            html = result.text.strip()
            # Strip markdown fences if present
            if html.startswith("```"):
                lines = html.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                html = "\n".join(lines).strip()
            # Validate it looks like HTML
            if "<!DOCTYPE" in html.upper() or "<html" in html.lower():
                return html
            # If Gemini returned JSON instead, try to extract
            doc = extract_json_object(html)
            if doc and "files" in doc and "index.html" in doc["files"]:
                return doc["files"]["index.html"]
            return get_html_fallback_game(design_doc.get("game_type", "arcade"))
        except Exception as e:
            logger.warning("Rich HTML game generation failed: %s", e)
            return get_html_fallback_game(design_doc.get("game_type", "arcade"))

    async def generate_complete_game(
        self,
        prompt: str,
        username: str,
        project_name: str,
        project_id: str,
        realtime: Any = None,
    ) -> GodotGenerateResult:
        """Orchestrate all agents to produce a complete Godot 4.x project.

        Phases:
          1. Design   — DesignAgent produces game_type, entities, mechanics
          2. Assets   — AssetAgent generates sprites in parallel + tileset + bg
          3. Scripts  — ScriptAgent generates .gd files in parallel
          4. Scenes   — SceneAgent generates .tscn files in parallel
          5. Assembly — main.tscn, project.godot, icon.svg, README.md
          6. Upload   — all files pushed to S3 under {username}/{project_name}/

        Args:
            prompt:       Natural-language game description from the user.
            username:     S3 path prefix (owner of the project).
            project_name: S3 path prefix (project folder name).
            project_id:   Used for WebSocket broadcasts only.
            realtime:     Optional RealtimeManager for progress events.

        Returns:
            GodotGenerateResult with S3 URLs, stats, and any non-fatal errors.
        """
        result = GodotGenerateResult()
        errors: list[str] = []

        # ── Phase 1: Design ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "design", "status": "running"})
        design_result = await self.generate_design(prompt)
        design_doc = design_result.payload
        result.design_doc = design_doc

        entities_raw = design_doc.get("entities", ["player"])
        entities = [_normalize_entity(e) for e in entities_raw]
        if not any(e["type"] in ("character", "player") for e in entities):
            entities.insert(0, _normalize_entity("Player"))

        await _emit(realtime, project_id, "godot_progress", {"phase": "design", "status": "complete"})

        # ── Phase 2: Assets ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "assets", "status": "running"})
        asset_tasks = [asset_agent.run(e, design_doc) for e in entities]
        asset_results = await asyncio.gather(*asset_tasks, return_exceptions=True)

        sprite_map: dict[str, dict] = {}
        for i, res in enumerate(asset_results):
            ename = entities[i]["name"].lower().replace(" ", "_")
            if isinstance(res, Exception):
                errors.append(f"Asset failed for {ename}: {res}")
                sprite_map[ename] = {"png_b64": None}
            else:
                sprite_map[ename] = res

        tileset_b64 = await asset_agent.generate_tileset(design_doc)
        bg_b64 = await asset_agent.generate_background(design_doc)
        await _emit(realtime, project_id, "godot_progress", {"phase": "assets", "status": "complete"})

        # ── Phase 3: Scripts ───────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "scripts", "status": "running"})
        script_tasks = [script_agent.run(e, design_doc) for e in entities]
        script_results = await asyncio.gather(*script_tasks, return_exceptions=True)

        script_map: dict[str, str] = {}
        for i, res in enumerate(script_results):
            ename = entities[i]["name"].lower().replace(" ", "_")
            if isinstance(res, Exception):
                errors.append(f"Script failed for {ename}: {res}")
                script_map[ename] = _fallback_script(entities[i])
            else:
                script_map[ename] = res

        await _emit(realtime, project_id, "godot_progress", {"phase": "scripts", "status": "complete"})

        # ── Phase 4: Scenes ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "scenes", "status": "running"})
        scene_tasks = [scene_agent.run(e, design_doc) for e in entities]
        scene_results = await asyncio.gather(*scene_tasks, return_exceptions=True)

        scene_map: dict[str, str] = {}
        for i, res in enumerate(scene_results):
            ename = entities[i]["name"].lower().replace(" ", "_")
            if isinstance(res, Exception):
                errors.append(f"Scene failed for {ename}: {res}")
                scene_map[ename] = f'[gd_scene format=3]\n[node name="{ename}" type="Node2D"]\n'
            else:
                scene_map[ename] = res

        await _emit(realtime, project_id, "godot_progress", {"phase": "scenes", "status": "complete"})

        # ── Phase 5: Assembly ──────────────────────────────────────────────
        game_name = design_doc.get("game_type", "game").title() + " Game"
        project_config = _generate_project_config(game_name)
        main_scene = _generate_main_scene(entities)
        icon_svg = _generate_icon_svg()
        readme = _generate_readme(
            design_doc.get("game_type", "arcade"),
            design_doc.get("mechanics", []),
        )

        # ── Phase 6: Upload ────────────────────────────────────────────────
        await _emit(realtime, project_id, "godot_progress", {"phase": "upload", "status": "running"})
        file_urls: list[dict[str, str]] = []

        # Text files
        text_files = {
            "project.godot": project_config,
            "scenes/main.tscn": main_scene,
            "icon.svg": icon_svg,
            "README.md": readme,
        }
        for ename, content in scene_map.items():
            text_files[f"scenes/{ename}.tscn"] = content
        for ename, content in script_map.items():
            text_files[f"scripts/{ename}.gd"] = content

        for filename, content in text_files.items():
            try:
                r = await s3_storage.upload_file_content(username, project_name, filename, content)
                if r.get("url"):
                    file_urls.append({"filename": filename, "url": r["url"]})
            except Exception as e:
                errors.append(f"S3 upload failed for {filename}: {e}")
                logger.warning("S3 upload failed for %s: %s", filename, e)

        # Binary PNG assets
        for ename, asset_data in sprite_map.items():
            b64 = asset_data.get("png_b64")
            if not b64:
                continue
            try:
                raw_bytes = base64.b64decode(b64)
                r = await s3_storage.upload_bytes_content(
                    username, project_name, f"assets/{ename}.png", raw_bytes, "image/png"
                )
                if r.get("url"):
                    file_urls.append({"filename": f"assets/{ename}.png", "url": r["url"]})
            except Exception as e:
                errors.append(f"S3 PNG upload failed for {ename}: {e}")
                logger.warning("S3 PNG upload failed for %s: %s", ename, e)

        # Tileset and background
        for fname, b64 in [("assets/tileset.png", tileset_b64), ("assets/background.png", bg_b64)]:
            try:
                raw_bytes = base64.b64decode(b64)
                r = await s3_storage.upload_bytes_content(username, project_name, fname, raw_bytes, "image/png")
                if r.get("url"):
                    file_urls.append({"filename": fname, "url": r["url"]})
            except Exception as e:
                errors.append(f"S3 PNG upload failed for {fname}: {e}")

        result.file_urls = file_urls
        result.errors = errors
        result.stats = {
            "entities": len(entities),
            "scripts": len(script_map),
            "scenes": len(scene_map),
            "assets": len(sprite_map),
            "files_uploaded": len(file_urls),
        }
        result.status = "partial" if errors else "complete"

        await _emit(realtime, project_id, "godot_complete", {
            "status": result.status,
            "file_count": len(file_urls),
        })

        return result

    async def chat_reply(
        self,
        message: str,
        project: dict[str, Any],
        history: list[dict] | None = None,
    ) -> OrchestratorResult:
        system = (
            "You are an expert game development assistant for the ForgeAI platform. "
            "Help users modify, debug, optimize, and improve their game projects. "
            "When shown existing code files, provide specific targeted changes with the full updated file content where relevant."
        )
        project_name = project.get("name", "the project")  # noqa: F841

        # Build a snippet of existing project files so the AI can answer
        # modification/edit questions with actual code context.
        _MAX_FILE_CHARS = 2000
        _MAX_FILES = 10
        existing_files = (project.get("generated_code") or {}).get("files", {})
        files_context = ""
        if existing_files:
            snippets = []
            for fname, content in list(existing_files.items())[:_MAX_FILES]:
                snippet = content[:_MAX_FILE_CHARS]
                if len(content) > _MAX_FILE_CHARS:
                    snippet += "\n... (truncated)"
                snippets.append(f"=== {fname} ===\n{snippet}")
            files_context = "\n\nEXISTING PROJECT FILES:\n" + "\n\n".join(snippets)

        history_text = self._format_history(history or [])
        full_prompt = f"{system}{files_context}{history_text}\nCURRENT REQUEST: {message}"
        try:
            result = await provider_manager.generate(full_prompt, temperature=0.7)
            return OrchestratorResult(summary="reply", payload={"reply": result.text}, usage=result.usage)
        except Exception:
            reply = f'Assistant noted for {project_name}: "{message}". I can generate design/code updates or profiling guidance.'
            return OrchestratorResult(summary="reply", payload={"reply": reply}, usage=ProviderUsage())


ai_orchestrator = AIOrchestrator()
