# Gameplay reference analysis and development plan

> Historical baseline from before implementation. Improvements have now begun; see [implementation progress](IMPLEMENTATION_PROGRESS.md) and the current [movement](../specs/MOVEMENT_AND_COLLISION.md) / [interaction](../specs/BLOCK_INTERACTIONS.md) specs. The project-status tables, original source anchors and file hashes below describe the earlier inspection.

Inspection date: 2026-10-17. Reference: [growtopia_gameplay.mp4](growtopia_gameplay.mp4). Implementation inspected: [root main.py](../main.py).

**Scope:** project inspection, visual evidence, comparison, and a proposed implementation order. No gameplay code, account data, or world data was changed. This is an observational baseline, not a claim to reproduce Growtopia's internal implementation. Recorded graphics remain reference material; future game art should be original or properly licensed.

## 1. Findings that matter most

The project already implements a playable local sandbox: movement, jumping, tile collision, camera following, mining damage, drops and pickup, block placement, an eight-slot hotbar, local profiles, world creation/selection, JSON saves, and lava hazards. These systems provide useful foundations and should be improved incrementally.

The largest differences visible in this recording are:

1. Repeated directional punching has a strongly visible extension/retraction and impact response. The project damages blocks only on individual mouse-down events; its punch animation is independent of damage.
2. Excavation exposes a second textured surface, and the player can occupy excavated spaces in front of it. Further punching clears that surface to the distant scene. The project has one tile layer.
3. The reference has distinct block and seed items, harvestable trees, a larger inventory drawer, and planting feedback. The project has only three collectible tile types and a hotbar that is also the inventory model.
4. The reference uses animated pixel art, connected terrain edges, layered scenery, and changing world scale. The project draws simple shapes at one scale.
5. The reference includes tutorial prompts, an ownership/lock event, contextual labels, and notifications. The project has local menus and an informational HUD but no corresponding progression or object interaction system.

Timing deserves attention before tuning values: the project already scales movement by elapsed time, but isolated checks found different jump heights at different update rates, and a long frame can resolve a falling player below the first crossed surface. This is an implementation finding, not a measured difference from the reference's physics.

## 2. Evidence, coverage, and limits

### 2.1 Recording metadata

Measured with local FFprobe; the complete output is in [video_metadata.json](analysis_frames/video_metadata.json).

| Property | Value |
| --- | --- |
| Container duration | 140.573605 seconds, approximately 02:20.574 |
| Video duration | 140.566667 seconds |
| Video | H.265/HEVC, 1280 x 720, 60/1 fps |
| Video frames | 8,434; zero-based indices 0 through 8,433 |
| Last decoded video frame | 02:20.550, index 8,433 |
| Audio | AAC, stereo, 44.1 kHz; not listened to or analyzed for sound timing |
| File size | 71,863,160 bytes |

The video frame rate is a capture property. It does not establish the original game's simulation rate or sprite-animation rate. The source includes black padding above/below the visible game and a narrow margin at the left. Those margins and the bottom device gesture bar should not be treated as game HUD elements.

### 2.2 Inspection method and timestamp meaning

Local FFmpeg and OpenCV were used; no external upload or automated video-description service was required. Review included:

- Two overview sheets, selecting source frames every five seconds.
- Nine coverage sheets, selecting source frames every second across the entire video, including 02:20.
- A jump sequence at 0.1-second intervals, a punch sequence at 0.05-second intervals, digging at 0.25-second intervals, placement at 0.2-second intervals, and a relocation sequence at 0.1-second intervals.
- Native-resolution stills for text, inventory, item counts, planting, and rejection messages.

Coverage and overview sheets use source presentation timestamps, not a new sampling clock. Close-up sheets label a starting offset plus the frame's local timestamp: `23.8s + 00:00:00.250` means **00:24.050**. Native still manifests record requested time, decoded time, and source frame index. See the [evidence index and extraction commands](analysis_frames/README.md).

All times below are **MM:SS**, optionally with milliseconds; for example **01:18 means 78 seconds**, not 118 seconds. Ranges identify evidence windows, not exact action durations. One-second sampling can miss short events; the entire recording was not annotated frame by frame. A timestamped screenshot proves what was visible at that instant, not the input, collision box, server rule, or reason behind it.

### 2.3 Evidence labels

- **Observed:** directly visible in inspected frames or readable interface text.
- **Measured:** metadata, decoded frame timestamps, or explicitly described local runtime measurements.
- **Inferred:** an explanation consistent with visible results, but not uniquely proved by them.
- **Unknown:** not established by this recording. No exact movement constants, action intervals, loot probabilities, or growth times are assigned to these unknowns.

## 3. Existing project inspection

### 3.1 Files, engine, and entry point

| Location | Finding |
| --- | --- |
| `main.py` | Active Pygame application, 1,567 physical lines; guarded entry point at line 1,566 |
| `accounts.json` | One local account; username, eight inventory slots, selected slot |
| `worlds.json` | One saved world; name, 86 x 100 tile array, spawn pair; current IDs 0-5 |
| `assets/` | Empty; current rendering uses Pygame shapes and system fonts |
| `src/` | Empty; systems are classes in `main.py`, not separate modules |
| `specs/` | Empty at inspection; no existing behavioral specifications to reconcile |
| `test/` | Empty; no checked-in automated tests or test configuration found |
| Dependency/setup files | No requirements file, packaging configuration, or launch README found |
| `growtopia-python/` | Contains `.git` metadata, without a second active `main.py` or JSON files |

The IDE's similarly named tabs should not be taken as two implemented versions. The workspace root has the active files. A read-only check of the nested repository reports its tracked `main.py`, `accounts.json`, and `worlds.json` absent there; the parent workspace is not itself a Git working tree. No files were moved, restored, or reorganized during this analysis. Establish the intended source-control root before a future implementation change.

The engine is **Pygame**, with a fixed 1600 x 900 display and a 60 FPS cap (`main.py:11`, `main.py:1494`). There is no separate physics engine, entity framework, network layer, or asset pipeline. The environment used for verification has Python 3.12.10, Pygame 2.5.8, and SDL 2.32.10.

### 3.2 Architecture and reuse boundaries

```text
Game: display, fonts, clock, local accounts/worlds, current scene
  MenuScene: choose a local username
  CreateWorldScene: create a world or select a saved world
  GameScene: input, camera, action coordination, effects, HUD, world drawing
    World: tile grid, generation, tile queries, spawn, serialization
    Player: movement, collision, damage, knockback, respawn, drawing
    Hotbar -> Account: selection, stacks, consumption, inventory persistence
    PunchAnim: timed visual punch
    DroppedItem: drop physics, bobbing, proximity collection
  Button / TextBox / WorldList: reusable interface widgets
```

| Component | Source anchor | Responsibility and useful seam |
| --- | --- | --- |
| JSON helpers | `main.py:151` | Existing load/save entry points; paths are relative to the process working directory |
| `Account` | `main.py:182` | Profile, inventory normalization, selected slot, serialization |
| `World` | `main.py:226` | Terrain generation, tile access, collision flags, spawn, coordinate conversion |
| World serialization | `main.py:328`, `main.py:336` | Existing save compatibility boundary; accepts legacy world-name strings too |
| `Player` | `main.py:350` | Position/velocity, grounded state, facing, collision, health and hazards |
| `PunchAnim` | `main.py:526` | Millisecond-based visual extension and retraction |
| `DroppedItem` | `main.py:565` | World item entity, gravity, grounded bobbing, proximity detection |
| Widgets | `main.py:641` | Button, text input, world list |
| `Hotbar` | `main.py:787` | Inventory operations and view currently share the same class |
| Scene interface | `main.py:925` | `handle_event`, `update(dt)`, `draw(surface)` |
| Menus | `main.py:933`, `main.py:989` | Local profile and world selection/creation |
| `GameScene` | `main.py:1080` | Coordinates player, world, hotbar, damage, drops, camera and rendering |
| Game root and loop | `main.py:1494`, `main.py:1550` | Initialize dependencies, dispatch events, update and draw |

These class boundaries can become modules one at a time when a change needs it. Splitting the entire file before improving behavior would add risk without resolving a measured gameplay difference.

### 3.3 Current mechanics and parameters

The values in this subsection are **implementation constants or code behavior**, not estimates of Growtopia.

| System | Current implementation |
| --- | --- |
| World geometry | 32-pixel tiles; 100 columns x 86 rows; surface row 40; bedrock begins row 80 |
| Tile types | Air, dirt, grass, stone, bedrock, lava; one foreground cell value |
| Generation | Flat grass surface; depth-dependent random dirt/stone; deeper random-walk lava pockets; bedrock floor/padding |
| Player dimensions | 28 x 56 pixels, or 0.875 x 1.75 project tiles |
| Horizontal movement | A/D or arrows; immediate nominal speed 4 pixels per 60 Hz step, approximately 240 pixels/second or 7.5 tiles/second |
| Jump | W, Space, or Up while grounded; nominal initial velocity -13; gravity 0.7 per nominal step; fall speed cap 18 |
| Held jump | Grounded polling permits another jump when a held key meets the ground again; no separate input-edge requirement |
| Collision | Horizontal and vertical axes resolved separately using integer `pygame.Rect` queries at destination positions |
| Timing | `dt` normalized against 60 Hz for movement/drop physics; millisecond-based action/effect timers; camera uses a fixed per-update factor |
| Camera | Follows on both axes with factor 0.15 per update, bounded to the world; additional horizontal viewport clamp on the player |
| Player drawing | Rectangular head/body, facing eye, health-related color changes; no sprite-based idle/run/jump cycle |
| Punch visual | 180 ms duration, earliest restart 60 ms; does not gate block damage; endpoints captured in screen coordinates |
| Mining input | Each left or right mouse-button-down performs the same selected-mode action; no held-button repeat in `update` |
| Mining rules | 4.5-tile center distance; dirt/grass need 2 hits, stone 4, lava 3; bedrock unbreakable; hit progress expires after 1,500 ms |
| Aiming | Mouse screen-to-world cell conversion; distance check, without line-of-sight testing |
| Drops | 33% chance of one block item per broken tile; lava yields stone; gravity, bobbing, 40-pixel proximity collection |
| Inventory | Eight account slots; slot zero reserved for fist; loaded collectible types restricted to dirt, grass and stone; stacks have no explicit maximum |
| Selection | Click hotbar, keys 1-8, mouse wheel; any empty slot means break mode, filled slot means place mode |
| Placement | Immediate when valid; 200 ms cooldown; 5.5-tile range; empty cell; cannot overlap player; no support/adjacency condition |
| Placement feedback | One ghost tile with valid/invalid border; not a multi-cell interaction grid |
| Health/hazard | 100 HP; lava non-solid and deals 25 HP/second, flashes/knocks back; regeneration 8 HP/second after 2.5 seconds without damage; immediate respawn |
| Lava timer detail | The 320 ms invulnerability variable gates repeated knockback, not continuous lava damage |
| Interface | Local username/world name, top banner, HP bar, depth label, eight-slot bottom hotbar, control hint, Exit button |
| Persistence | World name/grid/spawn and account inventory/selection; profiles are local names, not authenticated accounts |

Relevant action anchors: `_try_break` at `main.py:1172`, `_try_place` at `main.py:1200`, event handling at `main.py:1229`, camera update at `main.py:1253`, HUD at `main.py:1458`.

World edits serialize the complete world list immediately; placements and pickups also save accounts. Uncollected drops, per-tile damage, HP, player position, and camera are not serialized and reset when a new `GameScene` is created. The reference does not demonstrate exit/rejoin persistence, so these are project properties rather than verified reference discrepancies.

### 3.4 Systems absent from the code

There are no background-tile or world-object layers, seeds/trees/growth/harvest, item definitions separate from tile IDs, backpack/search/categories, equipment, recipes/splicing, doors/sign interactions, world ownership/permissions, onboarding objectives, notifications, currency, chat, networking, audio playback, world zoom, or sprite animation system.

Some of these are visible in the recording; others, especially networking, equipment use, recipes, and shop transactions, are **not demonstrated** and should not automatically become development requirements.

## 4. Recording timeline

This index covers the full recording. Detailed mechanics and uncertainty follow in section 5.

| Source time | Identifiable activity | Evidence |
| --- | --- | --- |
| 00:00-00:05 | Avatar at a furnished house/door, then travels right past flowers and a sign; welcome text appears nearby | Coverage 01 |
| 00:05-00:09 | Movement and successive jumps beside an elevated tree platform; controls brighten during use | Coverage 01; jump sheets |
| 00:09-00:23 | Traversal in both directions across stepped ground and gaps; tree hover/proximity labels; repeated lock prompt | Coverage 01-02 |
| 00:23.800-00:24.800 | Directional fist extends and retracts during movement; terrain remains visibly intact in this sampled window | Punch sheets |
| 00:24-00:30 | Repeated punches around nearby ground/trees; prompt to put the lock remains | Coverage 02 |
| 00:30-00:37 | Return toward the house; contextual tree and welcome labels | Coverage 02-03 |
| 00:38-00:40 | Select first world lock, perform placement, lock appears in world, selected stack disappears, ownership notice and fuller HUD appear | Coverage 03; native UI stills |
| 00:40-00:44 | Jump onto/over house area, then return toward sloped terrain | Coverage 03 |
| 00:44-00:50 | Repeated punching, white impact particles, cracks, and foreground excavation; discovery notice by 00:50 | Coverage 03-04; digging sheets |
| 00:50-01:11 | Continued excavation expands a walkable cutout; rough background remains in some cells and is cleared in others; items appear | Coverage 04-05; 01:05 native still |
| 01:11-01:16 | Move/jump out of excavated area toward the upper surface and trees | Coverage 05 |
| 01:15-01:19 | Dirt selection and floating block construction; inventory drawer briefly opens around 01:18 | Coverage 05; inventory close-ups |
| 01:20-01:22 | Punch harvestable dirt trees; falling seed messages, item/seed sprites and yellow collectibles appear | Coverage 06; harvest close-ups |
| 01:23-01:32 | Construct suspended horizontal blocks and a vertical pillar while jumping; faint grid around the avatar; changes of world scale | Coverage 06; placement sheet |
| 01:32.600-01:32.700 | View changes abruptly from a pillar to the house area; cause not established | Relocation sheets |
| 01:33-01:46 | Traverse house, excavation, and constructed platforms; more placement and jumping; another view return near the house at 01:46-01:47 | Coverage 06-07 |
| 01:47-02:00 | Jump around roof/nearby construction; add dirt above/beside avatar while climbing | Coverage 07-08 |
| 02:00.500-02:01.250 | Select Dirt Seed, count falls from 5 to 4, sprout appears, then planting discovery notice | Native seed close-ups |
| 02:01-02:08 | Move away; contextual Dirt Tree and Cave Background Tree labels on other trees | Coverage 08-09 |
| 02:09 | Seed use on a grown tree produces a too-big-to-splice message | Native rejection still; coverage 09 |
| 02:10-02:13 | Seed use on an unsuitable target produces a blank-tile/existing-tree restriction message | Native rejection stills; coverage 09 |
| 02:12-02:20.550 | Further harvest/collection increases carried dirt; traverse existing suspended platforms and excavated terrain, then return toward house | Coverage 09; final native frame |

## 5. Observable mechanics and their limits

### 5.1 Movement, collision, and camera

| ID | Time | Observed behavior | What it does not establish |
| --- | --- | --- | --- |
| M01 | 00:03-00:09; 00:16-00:23 | Avatar travels left/right across flat ground and changes facing; directional buttons change brightness | Exact acceleration, friction, speed, or release latency; touch brightness is not a calibrated input log |
| M02 | 00:05.800-00:07.900 | Avatar leaves the lower surface, rises/falls, lands on the raised surface, then jumps again | Exact gravity, launch velocity, variable jump height, input buffer, or held-jump policy |
| M03 | 00:14-00:23; 01:11-01:15 | Avatar crosses gaps and stands on different tile-height ledges | Automatic stepping, maximum jumpable obstacle, wall sliding, coyote time, or a second airborne jump |
| M04 | 00:49-01:11 | Avatar stands and moves through newly excavated space, with textured material behind parts of the space | Exact collision shape and background implementation |
| M05 | 01:23-01:32; 01:47-02:00 | Jumping and construction combine to reach suspended dirt and narrow pillars | Whether occupied-cell placement is possible; particles and body overlap obscure exact target cells |
| M06 | 00:05-00:09; 00:16-00:23; 01:47-01:55 | Terrain scrolls on both axes while the avatar stays near a central region; HUD stays anchored | Follow easing constant, dead zone, look-ahead, camera bounds, or screen-edge behavior |
| M07 | 01:22-01:24; 01:26-01:33; 02:14-02:19 | World objects/avatar change size relative to the largely fixed HUD; more/fewer tiles fit on screen | The gesture, zoom limits, zoom center, or whether every scale change is player controlled |
| M08 | 01:32.600-01:32.700; 01:46-01:47 | View returns abruptly from constructed terrain to the house vicinity | Death, respawn, teleport command, recording edit, or network correction; no cause is confirmed |

The 0.1-second jump samples show grounded poses near 00:06.800 and 00:07.500 with intervening airborne poses around 00:06.900-00:07.400. This is a useful comparison sequence, **not an exact flight-time measurement**: takeoff/landing occur between samples, the camera moves, and there is no recorded input trace. Use a future fixed-zoom recording to measure foot position relative to unchanged ground landmarks.

Apparent sprite dimensions should not be used as collision dimensions. The current collider is explicitly 1.75 project tiles tall; the recording has a different visual silhouette and variable display scale. Calibrate in tile units before altering the project's collider or physics.

### 5.2 Player and interaction animation

| ID | Time | Observed behavior | Limits |
| --- | --- | --- | --- |
| A01 | 00:03-00:09; 00:16-00:23 | Pixel-art avatar has different facing/leg/body poses during movement and in air | Full animation cycles, frame counts and idle blink timing were not isolated |
| A02 | 00:23.800-00:24.800; 00:25-00:30 | An elongated arm/fist projects toward a nearby direction and retracts; direction can be downward/diagonal | Exact reach, hitbox, cadence and whether taps or held input cause repetition |
| A03 | 00:44-01:11 | Punching produces repeated white pixelated impact bursts and crack overlays around targeted terrain | Particle lifetime, spawn count, exact damage tick, and whether every burst means a successful hit |
| A04 | 01:24.600-01:26.200; 01:51-01:59 | Block construction also has a hand/action pose and white particle feedback | Whether placement shares a complete animation state with punching |
| A05 | 00:00-00:05; 00:16-00:23; 01:20-01:22 | Torch flames, flying decoration, loose items and particles show changing poses or positions | Animation schedules, tree sway, material-specific effects, and audio synchronization |

No exact animation timing should be copied from the sparse samples. The project already has a timed punch helper, facing, velocity, and grounded state that can feed an original animation renderer.

### 5.3 World tiles, layers, scenery, and objects

| ID | Time | Observed behavior | Interpretation/limit |
| --- | --- | --- | --- |
| W01 | 00:00-00:05; 00:14-00:23 | Dirt-like terrain forms square-cell steps with a bright green upper edge and continuous diagonal fill | Logical tile pixel size, world dimensions and generation algorithm are unknown |
| W02 | 00:49-01:11, especially 01:05 | Smooth brown foreground is removed, leaving rough dark material behind accessible space; parts later reveal the distant purple scene | Strong evidence for separately rendered/collidable foreground and a background layer; exact data representation is inferred |
| W03 | 00:53-01:11 | Fresh interior floors also acquire a green top border | Consistent with neighbor-aware edge rendering; does not prove a separate grass item or automatic material conversion |
| W04 | 00:00-00:05; 01:33-01:37 | House has wood panels, stone framing/base, windows, railings, torches, a door and an EXIT label; flowers and sign stand outside | Collision flags and interaction behavior of each furnishing are untested |
| W05 | 00:00-00:05; 00:16-00:23 | Pale stone-like shapes appear embedded underground | Material identity, hardness and loot are not demonstrated; do not equate them with project stone without evidence |
| W06 | 00:00-00:23; 01:33-01:37 | Sky/mountains, clouds, sun, billboards and small flying decoration form layered scenery | Layer separation is visible; precise parallax factors and which props are gameplay objects are unknown |
| W07 | 00:10; 00:35; 01:14; 02:07 | Brown trees have a readable Dirt Tree label and a punch-to-harvest instruction | Full growth lifecycle and yield rules require more evidence |
| W08 | 01:26.200; 01:41; 02:06 | Dark branching objects are labeled Cave Background Tree with a harvest instruction | These should not be classified as enemies or NPCs from appearance alone; harvesting that type is not isolated |
| W09 | 01:24-01:26; 01:28-01:32; 02:14-02:20 | Suspended blocks/platforms remain in place while the player moves away | No universal gravity or support-collapse rule is shown; one block's placement may still depend on range/adjacency |

Lava, bedrock, water, weather changes, world boundaries, and deep underground generation are not established by this clip. Preserve the project's existing hazards while gathering evidence instead of removing them to match an unshown area.

### 5.4 Punching, mining, placement, and pickup

| ID | Time | Observed behavior | Limits/inferences |
| --- | --- | --- | --- |
| B01 | 00:09-00:35 | Repeated lock prompt accompanies punching with no comparable excavation visible | A tutorial/permission gate is plausible, but unsuccessful aim or targeting can also explain individual punches; no general lock permission rule is proved |
| B02 | 00:38-00:40 | Lock selected, action performed, lock appears near house; its hotbar item disappears; ownership toast and expanded HUD follow | Strong evidence for a consumed placement item and progression event; other-player permissions, removal and transfer are not tested |
| B03 | 00:44-00:50; 00:50-01:11 | Repeated impacts accumulate visible cracks and eventually change/remove terrain | Repeated-hit mining is supported; exact hits per material, hold-repeat policy and damage reset interval are not |
| B04 | 00:51.750; 00:57-01:10 | Excavation leaves a second material, and later impacts remove portions of that material | Foreground-before-background targeting is consistent with the sequence; simultaneous damage or exact target priority remains untested |
| B05 | 00:50-01:05; 01:20-01:22 | A dirt stack appears in the hotbar; distinct seed/boxed item sprites and yellow collectibles are visible near excavation/harvest | Precise pickup radius, attraction, item gravity and drop probabilities cannot be recovered reliably |
| B06 | 01:20-01:22 | A message explicitly reports falling Dirt Seeds; multiple item sprites/counts appear near trees | Seed drops are established, but per-tree yield, guaranteed versus chance-based drops, and stack limits are not |
| B07 | 01:17.500; 01:24.600-01:26.200; 01:51-01:59 | Dirt-use tooltip/placement result, then repeated selected-Dirt placement: blocks appear at grid cells, stack counts decrease, placement has particles | Exact cooldown, reach, line of sight, adjacency and player-overlap rules need controlled tests |
| B08 | 01:24-01:32; 01:50-02:03 | A faint local grid around the avatar appears during item use/construction, including airborne activity | It may communicate interaction reach; cell count and validation rules are not conclusively measured |

Mining particles partly obscure block transitions. Do not infer area-of-effect damage from cracks on several nearby cells, and do not infer the reference's hit count from the project's two-hit dirt rule. The observed sequence supports action feedback and progressive damage, not an exact internal schedule.

There is a useful pickup sequence with readable counts: at **01:21.000**, the hotbar still has 3 seeds while loose seed and framed block items remain on the lower step. By **01:22-01:23**, it shows 22 Dirt and 5 seeds, and the upper-left counter is 2. Subsequent construction decreases Dirt from 22 to 21 and then 19 across the sampled **01:24.500-01:26.000** interval. These are observed stack states, not proof of a fixed per-tree yield or pickup radius. Further harvesting/collection raises carried Dirt during **02:12-02:18**; this late sequence should not be mistaken for a new construction demonstration.

### 5.5 Hotbar and expanded inventory

| ID | Time | Observed behavior | Limits |
| --- | --- | --- | --- |
| I01 | 00:00-00:38 | Four visible quick slots near bottom center; fist in first, first world lock in second; selected border is yellow | Total inventory capacity is not four; these are only the visible quick slots |
| I02 | 00:38; 01:17.500; 02:00.500 | Contextual labels identify first world lock, Dirt, and Dirt Seed; Dirt and Dirt Seed show rarity 1 | Rarity's gameplay meaning is not demonstrated |
| I03 | 00:50; 01:05; 01:18; 02:00-02:01 | Stack counts are displayed; block and seed are separate items; selection changes border/action behavior | Maximum stack, sorting, overflow, drag/drop and hotbar assignment rules are unknown |
| I04 | 01:17.500-01:18.750 | Inventory drawer slides up, is open at 01:18/01:18.250, and closes; world remains visible; hotbar and action controls shift upward | Input during the open drawer and whether simulation pauses are not established |
| I05 | 01:18 | Drawer has a name search field, grid, left category icons, a green plus tile, search control and TRASH/STORE/DROP buttons; fist, wrench and seed stack visible | Labels/icons establish controls, not working search, storage, trash, drop, expansion, or wrench behavior |

The black `Dirt (Rarity: 1)` label still visible while the drawer is open does not prove the highlighted grid item is dirt; it can be an earlier contextual label. Avoid deriving item selection rules from that overlapping tooltip.

Representative full-resolution evidence: [inventory at 01:18](analysis_frames/ui_detail_078.00.jpg), [harvest at 01:21](analysis_frames/ui_detail_081.00.jpg).

### 5.6 Trees, planting, and seed rejection rules

| ID | Time | Observed behavior | What remains unknown |
| --- | --- | --- | --- |
| F01 | 00:10; 00:35; 01:14; 02:07 | Dirt Tree labels explicitly instruct punching to harvest; trees display block-like produce | Age at maturity, growth stages, grow time, watering/fertilizer, and exact yield |
| F02 | 01:20-01:22 | Punching the nearby dirt trees produces falling seed text and multiple item sprites | A clean punch-to-harvest count and per-tree reward distribution |
| F03 | 02:00.500-02:01.000 | Dirt Seed selected with count 5; by 02:01.000 count is 4 and a small sprout appears on the nearby lower step | Exact target validation, airborne seed/effect behavior, and time of the original input |
| F04 | 02:01.250-02:05 | A planting notification logs Dirt in the Seed Diary | The planted specimen's complete lifecycle; later tree labels are not proof this particular sprout matured |
| F05 | 02:09 | Seed use reports that an existing tree is already too big to splice another seed with | Successful splicing, compatible combinations, allowed growth window and recipes |
| F06 | 02:09.500-02:13 | Seed use reports that seeds can only be used on blank tiles or existing trees; the carried seed count remains 4 | Complete support rules, layer priority and all invalid-target conditions |

This clip supports a future **plant -> grow -> harvest** system at the feature level, but it does not supply reliable growth durations. Successful splicing should remain deferred until a recording shows it, rather than being invented from the rejection message.

### 5.7 HUD, menus, onboarding, and other visible behavior

| ID | Time | Observed behavior | Limits |
| --- | --- | --- | --- |
| U01 | 00:00-00:38 | Seed Diary objective strip at upper left, four-slot hotbar bottom center, left/right controls bottom left, jump/fist bottom right | Touch layout is reference-platform specific; desktop keyboard/mouse input can remain supported |
| U02 | 00:05-00:09; 00:23.800-00:24.800 | Movement/jump/action controls brighten and translucent circular touch feedback appears | Number of simultaneous fingers, gesture semantics and exact input onset are not logged |
| U03 | 00:09-00:35 | Repeated prompt requests the lock | Onboarding persistence, objective state machine and whether all early mining is forbidden |
| U04 | 00:39-00:43 | Ownership notification appears; upper-left player/counter panel, left shortcuts and right icons become visible | This is a visible HUD/progression transition, not evidence of multiplayer permission enforcement |
| U05 | 00:39-02:20 | Right side contains list/menu, chat with badge, face/emote and cart icons; top left has name/counter/plus; left has objective shortcuts | Menu contents, emotes, chat, purchases, and counter economy are not demonstrated |
| U06 | 00:50-00:54; 02:01.250-02:05; 02:09-02:13 | Teal bordered notifications announce discovery, planting and invalid actions | Exact fade/duration/queue rules are unknown |
| U07 | 00:04-00:05; 00:36-00:39; 01:34 | Welcome/sign-like contextual labels appear near the house | Whether triggered by touch, proximity, object selection or a tutorial event |
| U08 | 00:06.100; 00:51.750; 01:05 | Name/flag label follows the avatar; later name color differs from the early scene | Ownership/role/color rules and account customization are untested |
| U09 | 01:18; 01:22; 02:16 | Upper-left counter is 0, later 2, then 3; yellow gem-like items appear during harvest | A collectible counter is plausible, but currency rules, experience/level effects and spending are unproved |
| U10 | Entire recording | No sustained login/world-select/settings/shop/chat screen, second interacting player, health bar, or demonstrated hazard event is visible | This does not prove these systems are absent from the reference game |

The only clearly opened larger interface in inspected sequences is the inventory drawer. Existing local profile/world-selection menus cannot be meaningfully matched against unshown reference menus yet.

## 6. Feature comparison and priority

Priority is for the goal of improving the existing local game's observed feel. It is not a proposal to reproduce every reference feature.

| Feature | Reference evidence | Project status | Recommended treatment |
| --- | --- | --- | --- |
| Horizontal movement and jumps | M01-M03 | Implemented; nominal horizontal speed scales with `dt`; jump integration varies with update rate | **P1:** stabilize timing/collision first, then tune only against controlled evidence |
| Camera follow | M06-M07 | Follow exists; fixed factor per frame; no zoom | **P1:** make follow time-based; **P2:** optional zoom after transforms are separated |
| Terrain collision | M03-M05 | Implemented; long-frame penetration reproduced | **P1:** bound/substep simulation or sweep crossed tiles; retain existing solid-tile queries |
| Punch aim/repetition | A02, B03 | Aim/range and visual exist; click-only damage | **P1:** isolate action scheduling; investigate held-repeat versus taps before selecting cadence |
| Progressive damage/impact feedback | A03, B03 | Hit counters/cracks exist; punch does not govern damage; no impact particles | **P1:** reuse damage map and punch helper; synchronize clear feedback with accepted actions |
| Foreground/background excavation | W02, B04 | Missing second layer | **P1/P2:** evolve `World` and save schema without replacing existing terrain |
| Avatar animation | A01-A04 | Static geometric body, facing eye, timed fist | **P2:** original sprites or original procedural animation driven by current state |
| Connected terrain/scenery | W01, W03, W06 | Flat colors, one sky fill | **P2:** adjacency-aware original tile rendering, then scenery layers; keep collision independent |
| Drops and collection | B05-B06 | Basic drop entities and pickup exist | **P2:** retain entities; add item identities and reliable inventory transfer; leave reference probabilities unknown |
| Quick access inventory | I01-I03 | Eight-slot hotbar and stack operations exist | Preserve desktop convenience; four-slot presentation is optional, not a reason to shrink stored inventory |
| Larger inventory/item types | I04-I05 | Missing; `Account`/`Hotbar` coupled | **P2:** separate inventory model from hotbar view; add drawer after item IDs/save migration |
| Trees/seeds/planting | F01-F04 | Missing | **P2/P3:** implement after item model, world objects, timing, and supporting evidence |
| Splicing/crafting | F05 | Missing; only rejection shown | **P3/defer:** no successful behavior or recipe established |
| Context labels/notifications | U03, U06-U07 | Item text and hints only | **P2:** small reusable notification/context system; larger tutorial later |
| World lock/ownership | B01-B02, U04 | Missing | **P3:** optional local ownership/tutorial object; remote permissions require a separate design |
| House door/sign interactions | W04, U07 | Missing | Defer until recordings isolate entry/exit and sign activation; do not infer teleport from M08 |
| Menus/profile/world browser | U10 | Local versions already work | Preserve; reference equivalents not shown |
| HP/lava/respawn | No controlled reference evidence | Implemented | Preserve and test existing behavior; do not retune from this clip |
| Save/rejoin behavior | Not shown | Local JSON exists; transient entities reset | Improve save reliability when schemas evolve; reference persistence remains unknown |
| Audio | Stream present, not analyzed | No playback system | Later, using original/licensed sounds and a separate sound reference review |
| Chat, store, multiplayer | Icons/labels only | Missing | Defer; not needed for the next local gameplay milestone |

## 7. Verification performed without changing gameplay

### 7.1 Method and passed checks

`main.py` was compiled in memory and executed under a non-entry-point namespace. Pygame used dummy video/audio drivers, and the working directory was a temporary directory **before** `Game` initialization. All runtime-created saves therefore stayed outside the project. The actual `Game.run()` loop was also exercised with a queued quit event. No import bytecode or test scripts were added to the project.

Passed checks:

- Syntax compilation; menu initialization, update, drawing and display flip at 1600 x 900.
- Generated-world/game-scene initialization and ten update/draw frames.
- Normal `Game.run()` quit handling.
- Grass remains after the first accepted break call and becomes air after the second.
- Dirt placement consumes one item, rejects an immediate second placement during cooldown, and rejects player overlap.
- World/account serialization round trips using temporary files.

The unchanged renderer was also captured with dummy drivers: [current menu](analysis_frames/implementation_menu.png) and [current gameplay](analysis_frames/implementation_gameplay.png). The latter uses a generated world named `ANALYSIS FIXTURE` and a synthetic local profile, not the user's saved world/account. These provide a visual baseline against the [reference digging scene at 00:51.750](analysis_frames/detail_051.750.jpg); scale and framing differ, so compare system/layout/art differences rather than raw pixel positions.

The project baseline also exposes two presentation issues in this environment: the bottom control hint overlaps the hotbar, and the fist/some separator characters render as missing-glyph boxes with the selected system font. These are visible baseline findings, separate from the reference's art/layout differences; font fallback and HUD spacing can be addressed in a later presentation change.

The random no-drop branch was forced for deterministic breaking checks. The configured 33% drop chance was inspected in code, not statistically validated. Dummy drivers establish that render paths execute; they do not establish visible quality, actual input feel, audio output, or fidelity to the recording.

### 7.2 Measured project timing behavior

After settling a player on a flat generated surface, the harness simulated one second of rightward input and a single jump at different update rates. Jump input was released after launch. These are **project measurements**, not reference measurements.

| Update rate | Horizontal displacement in 1 s | Jump apex above starting position | Airborne time |
| --- | --- | --- | --- |
| 30 Hz | 240 px | 108.0 px | 600.0 ms |
| 60 Hz | 240 px | 114.3 px | 616.7 ms |
| 120 Hz | 240 px | 117.475 px | 616.7 ms |

All landed at their original ground height. Horizontal motion scales successfully; vertical Euler integration still changes the trajectory. Relevant code: `main.py:430` and `main.py:460`.

A separate stress check began 100 pixels above the surface at terminal downward velocity and issued one 200 ms update. The player resolved to `y=1320`, feet at row 43 instead of the first surface at row 40. Destination-only collision/correction (`main.py:482`) can resolve below the first crossed obstacle during a long frame. This is a reproduced project risk even though normal short-frame smoke checks pass.

### 7.3 Static concerns not reproduced as runtime failures

- Camera interpolation is a fixed 0.15 per update, so follow response depends on update frequency (`main.py:1255`).
- A grounded drop never rechecks its supporting tile; removing support may leave it floating (`main.py:594`).
- Punch origin/target are stored in screen coordinates; moving the camera during a punch may visually detach it (`main.py:1134`).
- Save errors are swallowed; writes are not atomic, have no schema version, and rewrite all worlds on every edit (`main.py:160`, `main.py:1195`).
- Relative save paths make launch working directory significant (`main.py:14`).

These are engineering considerations for targeted follow-up, not justification for a broad rewrite.

### 7.4 File preservation

SHA-256 hashes of `main.py`, `worlds.json`, and `accounts.json` matched before/after isolated verification. This analysis adds documentation and derived evidence only. No behavior changed, so no existing specification was replaced and `specs/` remains untouched.

| File | Preserved SHA-256 |
| --- | --- |
| `main.py` | `61E257EC05DF6580E93B2C030ED9DFE25DE715ACAA9D57F0A21FDF141A387646` |
| `worlds.json` | `B7EA1E0C27587B792D747018ED7BE0EDC426450E39457F113063AEE9491C0E93` |
| `accounts.json` | `3B0D136D66E298B99E9003024DA5D387D983656A85E2F9E11C8BDB3231F1F8FC` |

## 8. Recommended implementation order

All steps below are proposed future work. None was implemented as part of this inspection. Each is small enough to review and validate separately; do not combine the entire list into a rewrite.

| Order | Milestone and rationale | Reuse and scope | Completion evidence |
| --- | --- | --- | --- |
| 0 | Establish a safe baseline and intended source-control root | Preserve active root files and existing JSON; record controls; add a deterministic flat/stepped test fixture and targeted behavior specs when implementation begins | Existing saves still load; menus, movement, mine/pickup/place loop pass; no source-tree ambiguity |
| 1 | Stabilize simulation/collision and camera timing | Retain `Player` and `World.is_solid`; introduce bounded simulation steps or appropriate sweep logic; convert camera response to elapsed time | Consistent one-second travel and closely matching jump arcs at 30/60/120 Hz; no penetration during representative long frames; measured camera response |
| 2 | Make interaction input/action scheduling explicit | Retain `_try_break`, `_try_place`, hit map and cooldown checks; separate selected tool/item intent from mouse events and punch rendering | Clear accepted-hit/placement events, safe UI input routing, consistent action rate across frame rates; repeat policy chosen from better evidence or explicitly labeled original design |
| 3 | Improve visible movement and action feedback | Use existing facing/grounded/velocity and `PunchAnim`; add original animation/impact renderer, anchor action visuals in world space | Original idle/move/air/action poses; fist tracks player/camera; readable cracks and accepted-action particles; compare to M02/A02/A03 windows |
| 4 | Separate items, inventory and hotbar; harden transfer/save boundaries | Introduce item definitions distinct from tile IDs, reusable stack operations and a hotbar view over `Account`; keep current controls and migrate existing saves | Existing inventories preserved; block/seed identities can coexist; failed transfer does not destroy a drop; search/drawer can be added without replacing gameplay |
| 5 | Add layered excavation and neighbor-aware terrain rendering | Extend `World` with background/object data and a versioned migration; retain current foreground grid and collision queries | Foreground removal leaves non-solid background; clearing background reveals scenery; old worlds migrate and round-trip; original grass/edge art responds to neighbors |
| 6 | Add a minimal planting/growth/harvest loop | Build on item IDs, world objects, timers and drops; begin with one original tree/seed family | Valid plant consumes one seed; invalid target consumes none and explains why; growth/harvest persist; timings/yields have evidence or are explicitly chosen original values |
| 7 | Add inventory drawer, contextual labels, notifications and optional zoom | Reuse widgets/scene draw flow; keep input regions separate from world actions; centralize world/screen transform before zoom | Drawer does not mine/place through itself; selection/counts stay consistent; labels follow world objects; zoom leaves target picking accurate; desktop HUD scales sensibly |
| 8 | Consider local onboarding, lock objects and doors after core loop works | Extend object interactions and scene state; preserve existing menus and hazards | A short local objective loop has observable outcomes; door activation and ownership semantics are specified before coding |

Save safety belongs in the same change that expands the data model: introduce schema/version migration, explicit load/write failures, and atomic replacement where appropriate. Keep transient mining damage separate from persistent world data. Decide whether uncollected drops and growing trees should persist as a product behavior, then specify/test it.

New specs should be narrow and behavior-based, for example movement/collision, interactions, inventory, world layers, and farming. Record the reference IDs that motivate each rule and mark original choices clearly. Add regression coverage for meaningful state transitions and save migrations, not tests that only reproduce private implementation details.

Networking, real account authentication, trading, a store, economy balancing, comprehensive splicing, equipment, and exact commercial UI replication should remain outside the next local-game milestone. This recording does not provide enough evidence to specify them, and they would divert work from the visible sandbox loop.

## 9. Additional recordings that would resolve uncertainty

These are targeted future evidence requests, not prerequisites for reading this report or preserving current features. The existing clip is sufficient to plan incremental work.

| Priority | Suggested controlled recording | Questions it resolves |
| --- | --- | --- |
| High | Fixed zoom, flat unobstructed ground, visible button state: idle, hold right, release, reverse; several single jumps with short/long presses; walk off a ledge | Speed in tiles/second, acceleration/deceleration, jump height/time, variable height, held-jump behavior, coyote/buffer behavior |
| High | Stand still beside one labeled dirt block: separate taps, held action, pause midway, resume; repeat for background and stone; no camera/zoom movement | Hit count, action cadence, damage reset, foreground/background targeting and animation/hit relationship |
| High | Attempt placement at increasing tile distances, behind obstacles, unsupported, adjacent, overhead and intersecting the player | Reach shape, line of sight, adjacency/support, overlap rules, accepted/rejected feedback |
| High | Plant one labeled seed on an isolated platform; keep it in view from seed to mature tree; harvest once; show inventory before/after | Valid planting support, growth stages/time, harvest hits and exact observed yield; repeated trials needed for probabilities |
| Medium | Open inventory slowly; select categories, search, assign quick slots, use drop/trash/storage, reach a stack/capacity boundary | Inventory capacity, filtering, sorting, stack limits, transfer/overflow and drawer input behavior |
| Medium | Lock placement with nearby and distant targets; show permission failure with a second consenting test player; remove/rejoin | Ownership scope, permissions and persistence; separates tutorial behavior from general world rules |
| Medium | Enter/exit the visible house door, activate the sign, deliberately trigger a known respawn, and show relevant menu commands | Door/sign input and effects; cause of abrupt returns seen at 01:32.700 and 01:46-01:47 |
| Medium | Exit and rejoin after mining, leaving drops, planting, and moving away from spawn | Persistence of world edits, drops, growth, inventory and player position |
| Later | Clearly show zoom gesture and limits; a controlled hazard encounter; successful splicing with two labeled seeds; focused audio capture | Camera transform rules, damage/respawn, valid splice window/recipes, sound behavior |

Keep the original uncropped capture if possible and include an input overlay or deliberately separated presses. Measure movement against static tile landmarks, not screen coordinates while the camera or zoom changes. A few controlled examples are more useful for tuning than assuming exact values from this exploratory session.

## 10. Open decisions

- The intended desktop control scheme can retain eight quick slots and keyboard/mouse support; matching mobile controls is a separate scope choice.
- Reference physics, attack cadence, drop odds, tree growth durations and successful splicing remain unmeasured. Existing project constants should not be relabeled as reference values.
- The second terrain layer is strongly supported visually, while its exact material rules and targeting order still need isolation.
- Abrupt returns to the house have no confirmed cause. Do not implement death/teleport behavior from them alone.
- The next concrete development target should be reliable movement/collision plus clear action feedback, followed by item/layer foundations for the seed/harvest loop. Existing menus, saves, generation and hazards remain useful systems to preserve.
