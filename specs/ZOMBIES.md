# Zombie NPCs

Press **F6** in gameplay to spawn a zombie at a nearby supported, empty,
lava-free position. Repeated key events and paused gameplay do not spawn.
The scene supports up to fifty zombies. They are temporary entities for the
current world visit; existing JSON save formats are unchanged.

`src/zombie.py` owns IDLE, WANDER, CHASE, ATTACK, HURT and DEAD states.
`ZombieSettings` contains original, configurable tuning values: 100 HP,
10 damage per player punch, 12 damage per scratch, detection at ten tiles,
disengagement at thirteen, 180 ms hit-stun and 1,100 ms between attack starts.
Zombie melee detection uses a configurable 1.15 hitbox scale (48.3 px from
the 42 px base reach) while retaining facing and clear-line-of-sight checks.
When living allies stand between a zombie and the player, each can add up to
one tile of capped swarm reach (two tiles maximum); terrain still blocks hits.
Punch knockback uses a moderate horizontal impulse of 3.0 and upward impulse
of -3.5; taking a hit immediately cancels a scratch and prevents another one
until hit-stun ends.
Chase speed is 3.0 world units per simulation step; wandering remains slower.
The six-frame scratch uses durations in the zombie animation JSON; its fourth
frame performs one connection check. These timings are initial design choices,
not measured Growtopia behavior. Recovery interrupts attacks; death prevents
further hits, emits one existing particle burst and removes the NPC after 260 ms.

Player and zombie share `CharacterPhysics`, swept axis collisions, gravity,
jump velocity, damage flash and knockback helpers. Zombie input is generated
by its AI rather than player keys. Chase uses bounded A* over safe standing
positions. Adjacent safe standing tiles are grouped into platform regions.
Walking links join positions within a platform; jump and drop links between
platforms are accepted only after simulation through the same physics and tile
collisions. The local platform graph is cached by world and region. Block edits
record their tile so unaffected regions can keep their cached graph.
The navigator reports complete, partial staging, and unreachable results.
Complete routes are committed until invalidated, a terrain edit occurs, the
player changes tile, or a periodic bounded check finds a materially shorter
route. Partial routes end at a useful reachable staging point and are retried
from the zombie's new position after a short cooldown; partial results are not
cached as proof that a route is impossible. If bounded search cannot find a
platform route, a physics-validated local jump or safe drop toward the target
can be used as a recovery step. For a lower target, a safe drop is preferred
when available. Repeated identical genuinely unreachable searches are
suppressed until the target, terrain, or zombie start position changes.
For a genuinely unreachable result, the zombie also checks for a safe local
drop toward its last known player position and follows that direction until it
lands, then replans from the new platform.
Grounded lack of progress triggers a recovery replan. Searches stay local (up
to 32 tiles wide), with at most one search per simulation tick, so long routes
beyond that area remain unsupported. Lava and deep pits are rejected; solid
unreachable walls cause disengagement after 2.5 seconds without progress.

Jump transitions use APPROACH, PREPARE_JUMP, JUMP, LAND and CONTINUE controller
modes. The zombie reaches the planned takeoff point, commits to its airborne
direction, checks its landing, and temporarily penalizes a failed transition.
Press **F4** during gameplay to toggle the navigation overlay. It shows cached
platforms and walk/jump/drop links, the current route, the next landing and
takeoff markers, controller mode, and temporarily failed transitions.

Chase tracks recent player velocity and simulates a short, collision-checked
landing estimate for airborne targets. It remembers the last seen position for
3.5 seconds while the player is just outside detection range. Losing a chase
transitions to WANDER toward that last position with no blind interval; the
zombie can re-engage immediately when the player returns to detection range.
Player death separately grants zombies a short respawn grace period. Zombies
receive small horizontal approach offsets to reduce crowding; offsets fade
within three tiles and a completed tile-sized path continues with safe local
movement until melee range. Their movement and collision remain physical.
Predicted player landing positions are
cached per world/player motion sample so a group shares the same trajectory
simulation. Synchronous route searches remain limited to one per simulation
tick, while spawn candidates spread across a wider safe area.
Player and living zombies also receive a small, block-safe horizontal
separation correction when their bodies overlap; each actor is shifted by at
most three pixels per simulation step, allowing soft contact without hard
entity blocking.

Player punches intersect the nearest enemy's float 28x56 hurtbox along the
aimed segment. They share the existing global 200 ms damaging-punch cooldown
with blocks and require clear tile line of sight. A targeted enemy consumes
the interaction instead of damaging a block behind it. Placement rejects
tiles occupied by living enemies. Scratches respect player invulnerability,
use the existing red flash/knockback, and share the existing death/respawn path.
Living enemies show a small HP bar briefly after damage. No new sound files
are required; accepted player hits reuse soft-hit feedback at reduced volume.

The supplied originals are actually in `assets/zombie/`. They are opaque and
have baked black/white/checkerboard backgrounds; the attack strip is irregular.
`tools/prepare_zombie_assets.py` preserves them and prepares transparent uniform
28x56 sheets in `assets/characters/zombie/`. The renderer crops the shared
occupied area across all zombie states, preserving the feet anchor and pose
proportions; nearest-neighbor rendering produces approximately 61px characters.
Background thresholding and reduced detail are limitations of these supplied
sources; true transparent pixel-art originals would improve edge quality.

`PlayerAnimation` supports a clamped full-body action and optional preserved
canvas anchoring. Zombie sheets and durations load through `AssetManager`;
normal animation and cached flash tints stay shared with the player. The small
entity list updates at the scene's fixed timestep; drawing culls offscreen NPCs.

Tests: `python -m unittest test.test_zombie test.test_animation test.test_physics`
and the normal full suite. A headless visual check is saved at
`references/implementation_checks/zombie_preview.png`; no manual playtest is claimed.
