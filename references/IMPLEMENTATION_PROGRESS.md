# Implementation progress

## 2026-10-17: stable simulation and first action-feedback milestone

Implemented in the existing Pygame architecture:

- Fixed 60 Hz scene simulation independent of rendering; original movement/jump constants retained.
- First-crossed-boundary tile collision for players and drops, including long frames and fractional coordinates.
- Camera/hazards/action timers use the same simulation clock; short jump taps survive between ticks.
- Resting drops recheck their support after tiles change.
- Immediate click input retained; holding adds repeated punching/placement with safe cancellation and UI filtering.
- World-anchored extending fist; original white impact puffs, stronger break debris and placement particles.
- Original drawn fist icon and readable bottom instructions separated from the hotbar.

No JSON schema change was needed. Existing saves are tested through read-only loading and temporary round trips. The nested repository layout was not repaired or moved; the active implementation remains the root `main.py` and its `src/` helpers.

Current behavior is specified in [movement and collision](../specs/MOVEMENT_AND_COLLISION.md) and [block interactions](../specs/BLOCK_INTERACTIONS.md). The [reference analysis](GAMEPLAY_ANALYSIS.md) remains a historical pre-implementation baseline; its old source line numbers and project-status tables describe that inspection, not the updated code.

## Verification

```powershell
python -B -m unittest discover -s test -v
```

The regression suite covers movement/jump/camera consistency at 30/60/120/144 Hz, swept collisions, long-frame behavior, drops, mine/pickup/place, cooldowns, existing saves, controls, UI routing, held actions, focus and effects. Tests use dummy SDL drivers and temporary saves. The real account/world files are checked for unintended changes.

Result: **45 tests passed** (35 gameplay/integration tests and 10 collision tests). Syntax and documentation-link checks passed. The real `accounts.json` and `worlds.json` SHA-256 hashes still match the pre-implementation baseline. The actual game loop's quit/save path and profile/create/select-world menu flows were exercised. No manual interactive playtest was performed.

See [visual checks](implementation_checks/README.md) for baseline/hit/break/place screenshots. Reference comparisons are qualitative: directional extension and white pixel bursts are supported by A02/A03/A04; exact reference timing, reach, hardness, loot odds and hold semantics remain unmeasured. Existing 180 ms visual timing and the new matching hold interval are project choices, not recovered reference values.

At most 250 ms is simulated after one frame; excess stall time is intentionally discarded. A focused-out scene pauses. Rendering remains capped at 60 FPS by default; render interpolation and a human interactive feel assessment remain future refinements.

## Next recommended increments

1. Add original grounded/moving/air poses without changing the collider, and compare against A01 at a fixed zoom.
2. Separate item definitions/inventory data from hotbar presentation while preserving existing stacks and saves.
3. Add foreground/background excavation through an explicit save migration, based on W02/B04.
4. Build the minimal seed/plant/grow/harvest loop only after item/object foundations exist; keep unmeasured growth/yield choices explicit.
