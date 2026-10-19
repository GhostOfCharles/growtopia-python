# Implementation feedback screenshots

These images document the first implemented action-feedback increment. They are
renders of this project's original procedural artwork, not frames or assets
copied from the reference recording. The existing historical evidence in
`../analysis_frames/` is preserved.

## Synthetic fixture and timing

The fixture uses a new flat dirt world named `Original action feedback review`,
player spawn `[50, 40]`, and an isolated `Feedback review` profile. A fixed camera
keeps the player, action target, and HUD directly comparable. The effects RNG is
seeded with 42. Breaking forces the existing no-drop outcome so loose loot does
not hide the impact effect; no loot probability is measured by these images.

Each action screenshot shows a pose **80 ms after its synthetic accepted
action**. This is elapsed implementation animation time, not a timestamp in
`growtopia_gameplay.mp4`. The punch and effects helpers are advanced directly
while the fixture remains static. For the break screenshot, a first dirt hit is
followed by 180 ms of visual animation, then the breaking hit and another 80 ms.
Some debris from the first hit can remain. The placement fixture starts with two
dirt blocks and visibly has one left after placing.

The retained 180 ms punch duration and the particle appearance, counts, speed,
and lifetime are original implementation choices. These screenshots do not
establish the reference game's action cadence or particle timings.

## Files

| File | Contents |
| --- | --- |
| [feedback_idle.png](feedback_idle.png) | Native 1600 x 900 baseline fixture and HUD |
| [feedback_hit.png](feedback_hit.png) | Accepted dirt hit, extended fist, cracks, puffs and chips |
| [feedback_break.png](feedback_break.png) | Dirt removed, stronger impact burst, extended fist |
| [feedback_place.png](feedback_place.png) | Placed dirt, action feedback and decremented hotbar count |
| [feedback_contact_sheet.png](feedback_contact_sheet.png) | The four full views, reduced to 800 x 450 each |
| [feedback_detail_sheet.png](feedback_detail_sheet.png) | The same action area cropped and enlarged 3x with nearest-neighbor scaling |
| [feedback_manifest.json](feedback_manifest.json) | Machine-readable fixture, timing, and reference-window notes |

## Reference comparison and limits

- [Punch sheets](../analysis_frames/punch_01.jpg) and
  [continuation](../analysis_frames/punch_02.jpg), source **00:23.800-00:24.750**
  (A02): directional extension and retraction motivate the world-space fist.
- [Digging sheet](../analysis_frames/dig_01.jpg), source
  **00:48.000-00:50.750**, and
  [native detail](../analysis_frames/detail_051.750.jpg), source **00:51.750**
  (A03): white impact bursts and progressive cracks motivate accepted-hit
  feedback. The implementation's smaller geometric effects are an original
  interpretation, not a pixel or timing match.
- [Placement sheet](../analysis_frames/placement_01.jpg), source
  **01:24.600-01:26.200** within the sheet (A04): construction includes an action
  pose and particle feedback.

Rendering used SDL dummy video/audio drivers. Save paths pointed to a temporary
directory before game initialization; the real profiles and worlds were not
used or written. These stills verify render paths and visible layout, including
the separate bottom control hint and drawn fist icon. They do not verify human
input feel, display latency, audio, a complete animation cycle, camera tracking
while moving, or the appearance at other world scales. Behavioral regression
tests provide separate coverage for simulation, collision, action routing,
timers, and save compatibility.
