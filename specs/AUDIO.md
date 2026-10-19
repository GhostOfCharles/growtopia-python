# Gameplay sound effects

`src/audio.py` loads WAV files from `assets/sounds/` once, case-insensitively,
and plays them through a bounded Pygame mixer channel pool. Mixer or individual
file failures disable only unavailable sounds. `AudioManager.set_volumes(master, sfx)`
configures the two volume multipliers.

Event mapping: successful stone destruction uses `block_hard`; dirt, grass, and
other breakable tiles use `block_soft`; actual jump initiation uses `jump`; a
grounded item pickup uses a cached version of `item_drop` pitched two semitones
higher (airborne pickups stay silent to avoid
stacking with jump/fall movement); jump and grounded pickup use the same
replaceable movement channel, so jumping stops any lingering pickup tail;
successful block placement uses `block_placed`; changed hotbar selection uses
`hotbar_select`; burn
damage and lethal damage use `burn` and `death`; entering and leaving gameplay
use `enter_world` and `leave_world`. Rejected placement attempts use
`cant_place` with a 350 ms cooldown; continuous burn uses a 900 ms cooldown.
Each accepted punch against a breakable tile also uses `block_hit_hard` for
stone or `block_hit_soft` for softer tiles. These hit sounds share a dedicated
replaceable channel so repeated punches provide feedback without stacking; the
final hit still plays the corresponding destruction sound at reduced hit-layer
volume. Hit, destruction, and placement sounds use five cached variants within ±0.4
semitones. Dirt and grass have four-hit durability, stone has ten, and the
`BLOCK_DURABILITY` table in `main.py` configures durability by block ID.
Successful block hits are globally limited to one every 200 ms (five per
second); held mining uses the same cadence, while the first click remains
immediate.
`equip.WAV` is loaded for future equipment actions but remains unused because
the game has no separate equipment action. No sound is played for failed block
breaks or for selecting the already active slot.
