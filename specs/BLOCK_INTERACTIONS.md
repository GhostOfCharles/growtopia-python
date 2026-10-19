# Punching, block feedback, and desktop input

Implemented 2026-10-17 using `GameScene`, `PunchAnim`, `Hotbar` and original procedural graphics in `src/effects.py`.

## Evidence and original choices

The [recording analysis](../references/GAMEPLAY_ANALYSIS.md) establishes extending/retracting directional punches (A02, 00:23.800-00:24.800), progressive cracks and white impact bursts during mining (A03/B03, 00:44-01:11), and placement feedback (A04/B07, 01:24.600-01:26.200). The [frame index](../references/analysis_frames/README.md) links those sequences.

The recording does not establish exact cadence, particle lifetime/count, input hold policy, block hardness or reach. This implementation retains existing project rules and adds explicitly original desktop convenience and presentation choices. No reference images, sprites, sounds or proprietary assets are loaded by the game.

## Actions and responsiveness

- Left and right mouse buttons keep the same selected-mode action. Any empty selected slot means punch; a nonempty stack means place.
- A world mouse-down attempts an action immediately; successful damaging punches share a global 200 ms cooldown across blocks and enemies. Damage is committed on accepted input, without waiting for the visual fist to reach the target.
- Holding a button repeats punching every 200 ms, independently of the retained 180 ms visual animation. Timer remainder is retained, giving the same accepted-action schedule across render rates, quantized to 60 Hz simulation ticks.
- Held placement retries at the existing 200 ms placement interval. The existing placement cooldown remains authoritative for both clicking and holding; floating-point epsilon permits an action exactly at that interval.
- The pointer's current screen position is converted with the current camera for every attempt. Moving the pointer changes the target; it is not locked to the initial block.
- Mouse release, focus loss, scene exit, respawn, selection changes and placement-stack depletion cancel the held action. Exhausting a stack cannot silently turn held placement into mining.
- A press beginning on the interface cannot start a world hold by dragging out. Holding from the world pauses attempts while the pointer is over interface/outside the window, and may resume when it returns. Explicit selection changes require a fresh press.

Protected interface regions include the top banner, HP/depth panels, complete hotbar panel including labels/gaps/lower edges, the bottom instruction strip and Exit button. Placement ghosts are also hidden over these regions. Number keys 1-8, wheel selection and normal hotbar clicks remain supported.

## Rules retained

| Behavior | Project rule |
| --- | --- |
| Punch range | 4.5 tiles, center distance |
| Dirt / grass hardness | 4 accepted hits |
| Stone hardness | 10 accepted hits |
| Lava hardness | 3 accepted hits; loot type stone |
| Bedrock | Unbreakable |
| Mining damage reset | 1,500 ms without another accepted hit |
| Loot | Existing 33% chance of one tile item on break |
| Placement | Empty cell, 5.5-tile range, positive inventory, no player overlap, 200 ms cooldown |
| Adjacency / line of sight | Block rules retained; enemy punches require clear tile line of sight |
| Persistence / inventory | Existing local JSON formats and eight slots retained |

An in-range punch toward air or bedrock animates for feedback but does not damage, create hit particles, generate loot or write a world save. Out-of-world/out-of-range attempts do not extend the fist.

An enemy hurtbox intersecting the aimed punch segment takes priority over the
block behind it. Entity combat, full-body scratch animation and developer
spawning are described in [ZOMBIES.md](ZOMBIES.md).

## Visual feedback

The punch target is stored in world coordinates; drawing uses the player's current center as the arm origin and subtracts the current camera. Moving the player/camera during a swing no longer leaves a detached screen-space arm. The retained 180 ms extend/retract curve remains visual and does not gate damage.

Each accepted hit emits short-lived white pixel puffs plus material-colored chips. Breaking emits a stronger burst. Accepted placement emits its own puff/chip burst. Invalid attempts do not create success effects. Particles are world anchored, time based, non-colliding and capped at 192 per scene. Their random generator is separate from gameplay randomness so extra feedback cannot alter terrain generation or loot rolls.

Particle sizes, speeds, counts and 120-320 ms lifetime ranges are original presentation settings, tuned through screenshots for visibility at 32-pixel tile scale. They are not measurements of the reference. Existing crack progress remains visible after the short burst fades. No screen shake, sound or material-layer change is included.

### Player animation

`src/animation.py` owns idle, walking, jumping and falling clips, original temporary procedural sprites, and the independent `PunchAnim` overlay. `GameScene` updates locomotion after each fixed physics tick using grounded state and velocity; animation never modifies the collider, physics or saves. The render path only draws poses. Punching adds an upper-body pose and the existing directional fist without replacing walking/jumping/falling.

Per-frame durations are configurable through `FRAME_DURATIONS_MS` or `PlayerAnimation(frame_durations=...)`; the retained punch duration is configured by `PUNCH_DURATION` in `main.py`. Idle/walk/fall loop, jumping holds its last pose, and changing locomotion state restarts its clip. Temporary timings and poses are original choices based on A01/A02 observations, not measured reference sequences.

The fist icon is drawn procedurally, avoiding dependence on emoji font support. The hotbar is raised slightly to make room for a separate instruction strip, with ASCII instructions that remain readable with the current system font.

## Verification and remaining differences

`test/test_gameplay.py` verifies immediate clicks, held timing at 30/60/120/144 Hz, release/focus/selection/depletion cancellation, UI exclusion, fractional placement rejection, particle lifetime/pool bounds, separate loot randomness, world-space fist drawing, and existing mining/pickup/place/save behavior. All save writes are isolated.

Visual check artifacts are in [references/implementation_checks](../references/implementation_checks/README.md). Headless screenshots verify rendered output, not a human playtest of keyboard/mouse feel.

The next steps are clearer world/item foundations: separate item definitions/inventory from the hotbar, then add foreground/background excavation with compatible save migration. Tree growth, a larger inventory drawer, world locks and precise reference tuning remain future work.
