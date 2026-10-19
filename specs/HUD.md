# Gameplay HUD

Gameplay HUD layout and drawing live in `src/hud.py`; the hotbar retains its
existing inventory model and selection controls. The layout derives positions
from the target surface size and offers a small HUD scale setting in the pause
menu.

Press **Escape** or click the pause icon to pause. The pause panel provides
Resume Game, Settings, Controls, and Save and Exit. Pausing cancels held actions
and stops simulation updates; Save and Exit writes the current world and
account data using the existing formats. Press **F3** to toggle player
coordinate and velocity diagnostics; coordinates are hidden by default.
