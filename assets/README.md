# Game assets

Place files under `characters/`, `blocks/`, `items/`, or `interface/`. Use transparent PNGs for pixel art. `characters/player/animation.json` configures the player clips. Its sample image paths are optional: missing sheets use the current procedural player poses.

Terrain textures are `blocks/dirt.png`, `grass.png`, `stone.png`, `bedrock.png`, and `lava.png`, each rendered at 32 × 32 px. The game loads and nearest-neighbor caches them at world, hotbar, and dropped-item sizes; missing files fall back to the original colored tiles. In the world, shared edges are flattened with cached neighbor variants so the source outline remains on exposed terrain edges instead of every tile seam.

## First character sprite

Export each frame on a **28 x 56 px transparent canvas** when possible, with the character centered and its feet at the bottom. Larger uniform frames also work: set their source dimensions in `frame_size`; the renderer uses one shared transparent crop for frames with the same source canvas, then scales proportionally with nearest-neighbor sampling. Put frames in a horizontal row in `assets/characters/player/animations/` and save the sheet under the state name, such as `walking.png`. In `animation.json`, set that state's `frame_size`, `count`, and one `durations_ms` value per frame. For separate files, replace `sheet` and its slicing fields with `"frames": ["characters/player/animations/idle_0.png", "characters/player/animations/idle_1.png"]`. Paths are relative to `assets/`.

The original `player_sprinting.png` has poses that cross equal-width sheet cells. Run `python tools/prepare_sprint_frames.py` after replacing it to rebuild the six complete transparent frames in `characters/player/animations/sprinting/`; the animation config loads those frames.

The renderer anchors each frame at the physics body's bottom center, scales with nearest-neighbor sampling, and mirrors it to face left. Keep all body frames on the same canvas so their feet do not jitter. An optional per-state `render_scale` in `animation.json` makes small visual size adjustments without changing collision dimensions. The `punch` sheet replaces the locomotion sprite while punching; leave the extended arm transparent because `assets/effects/punch-stretch.png` supplies that arm.

Run `python tools/validate_assets.py` to check PNG sizes, alpha transparency, and consistent frame dimensions within animation folders.
