# Movement, timing, and tile collision

Implemented 2026-10-17 in root `main.py` and `src/physics.py`.

## Intent and reference limits

Preserve the project's nominal 60 Hz movement feel while making simulation independent of rendering frequency. Reference IDs M01-M06 in [GAMEPLAY_ANALYSIS.md](../references/GAMEPLAY_ANALYSIS.md) establish traversal, jumps, tile contact and camera following. They do not establish exact speed, gravity, jump timing, collision dimensions, input buffering or camera easing. The parameters below are retained project choices, not measured Growtopia values.

## Simulation contract

- `GameScene.update(elapsed_ms)` accumulates elapsed time and calls `_simulate_step` at `SIMULATION_STEP_MS = 1000 / 60` milliseconds.
- Character physics, drop floating/pickup, lava damage/knockback/regen, camera following, action repeat, damage progress, placement cooldown and effect lifetimes use those fixed ticks. Rendering performs no simulation.
- Fractional time is retained between calls, including calls shorter than one tick. `FPS` limits rendering and does not define physics constants.
- Each call accepts at most `MAX_FRAME_MS = 250` milliseconds, allowing at most 15 simulation steps. Excess time after a very long stall is discarded instead of creating an unbounded catch-up loop. Simulation intentionally slows during such stalls; no claim of elapsed-wall-time parity is made beyond this bound.
- Focus loss pauses the scene, clears pending jump/held mouse actions and the time accumulator. The first update after focus gain is discarded so suspended wall time is not replayed. A fresh mouse press is required to resume a held action.
- `Player.update` and `DroppedItem.update` are simulation-step methods. Cross-render-rate consistency is provided by `GameScene.update`; external callers should not replace the fixed scene clock with variable entity steps.

## Movement preserved

| Parameter | Project value |
| --- | --- |
| Tile size / world dimensions | 32 px / 100 x 86 cells |
| Player collision dimensions | 28 x 56 px |
| Horizontal speed | 3 px per tick = 180 px/s |
| Sprint speed | 1.5x normal (4.5 px per tick = 270 px/s) while Shift and a horizontal direction are held |
| Jump launch velocity | -13 nominal px/tick |
| Gravity | +0.7 nominal px/tick per tick |
| Maximum downward velocity | 18 nominal px/tick |
| Camera follow | Existing 0.15 interpolation, now evaluated once per fixed simulation tick |

A/D or Left/Right move immediately; W, Space or Up jump when grounded. Holding jump still permits another jump on landing. A key-down arriving and being released between two simulation ticks is retained for the next tick only; an airborne press is consumed without adding coyote time, a landing buffer, or an airborne jump.

Holding either Shift key with horizontal movement increases input speed by 50%
until released, including while airborne. The shared swept-axis collision
resolver checks the full sprint displacement, so the higher speed does not
skip solid tiles. The player animation selects the configured six-frame sprint
clip only while grounded; jumping and falling retain priority in the air.

The normal 60 Hz jump retains the prior approximately 114.3 px apex above launch. Floor contact now uses precise float bounds instead of truncating the body to integer pixels. Rendering converts to pixels at draw time.

## Collision contract

`src.physics.sweep_axis` accepts a world with `is_solid(column, row)`, a float body rectangle, a displacement, axis and tile size. Movement resolves horizontal then vertical axes. Each sweep checks crossed tile rows/columns in travel order and stops at the **first** solid boundary, including contact exactly at the destination. This prevents skipping a thin obstacle even for a direct, unusually large entity update.

The perpendicular interval is half-open: merely sharing an edge with an adjacent tile does not block sliding. Floor contact zeroes downward velocity and marks the player grounded; ceiling/wall contact zeroes the relevant velocity. Existing world tile collision flags and world boundary queries remain authoritative. Spawn recovery from an already embedded or malformed save is not added in this change.

Placement overlap tests use the same float body dimensions. Subpixel overlap is rejected; exact edge contact is permitted. Lava's existing overlap query remains pixel-quantized, so subpixel hazard detection may lag contact by less than a pixel; lava damage rules were preserved. Taking damage triggers a 140 ms visual red flash on procedural and sprite-based player poses; the tint does not affect collision or physics.

Dropped items now float near their spawn tile with a time-based pop/bob and
retain radius-based pickup. They do not use gravity or terrain collision.

Player and zombie bodies use `integrate_character` and `CharacterPhysics` from
`src/physics.py`; input and AI remain separate. See [ZOMBIES.md](ZOMBIES.md).

## Horizontal dash

Press Q for an immediate horizontal burst using A/D (or left/right arrows),
falling back to the current facing direction when there is no directional input.
Direction and facing remain locked through the burst. `DASH_DISTANCE_TILES` (4)
and `DASH_SPEED_MULTIPLIER` (3) determine the duration: 128 px at three times
walking speed takes approximately 237 ms. The final movement step is
shortened to preserve the exact dash distance. `DASH_COOLDOWN_MS` is a separate
1000 ms recovery after completion or interruption. Holding Q does not repeat it.

Gravity and vertical velocity are suspended during the burst, preserving a
straight trajectory even while jumping or falling. Downward velocity resumes afterward, while upward jump momentum is cleared.
Normal gravity resumes for the remaining time in that step. Jump inputs held
during a dash must be released before jumping again, preventing a delayed jump. Horizontal tile collisions and world boundaries interrupt the burst using
the shared swept collision solver. Damage also interrupts it.

The four-frame full-body clip loops only during the actual burst and immediately
returns to normal movement animation afterward. The original source is preserved;
`python tools/prepare_dash_frames.py` rebuilds the normalized 112x56 sheet.

Each accepted dash emits one world-anchored pressure ring behind its starting
position and plays `dash_sound.WAV` through the cached audio manager. The broken
pixel arcs expand and fade over 260 ms with a few forward air streaks; visual
settings live in `BlockEffects`. Cooldown attempts emit neither sound nor ring.

## Heavy landing recovery

Heavy landings require a strictly greater than 10-tile actual descent from the
airborne apex to solid contact. Lava overlap and death suppress recovery. The
six-frame `heavy_landing` clip plays once over a 1000 ms movement/action lock;
held inputs require release before reuse. Support removal, displacement or
knockback interrupts recovery. Damage, enemies, particles and camera continue.
Shorter falls retain ordinary landing dust; heavy falls emit one larger,
material-colored burst lasting 520–780 ms. Settings live beside player physics
in `main.py` and in `BlockEffects`.

`FallingCamera` smoothly zooms toward 1.10 after six tiles of descent and eases
back to 1 during recovery. Zoom affects world rendering and matching mouse
conversion only; HUD and physical world coordinates stay independent. Death
resets it. No camera shake is applied. The source `heavy-landing.png` is preserved;
`python tools/prepare_landing_frames.py` rebuilds its six normalized frames.

## Verification

Run from the workspace root:

```powershell
python -B -m unittest discover -s test -v
```

`test/test_physics.py` covers first-obstacle sweeps in all four directions, exact contact, sliding, fractional coordinates and negative cell boundaries. `test/test_gameplay.py` covers scene behavior across 30/60/120/144 Hz, long-frame floor/wall/ceiling cases, drop support, controls, hazards and save compatibility. Tests redirect writes to temporary files and verify the original JSON files remain byte-identical.
