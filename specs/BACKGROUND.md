# Procedural sky background

Gameplay renders a cached vertical blue gradient and a seeded set of pixel
clouds before terrain. `src/background.py` owns background visuals only; it does
not affect world coordinates, collision, or saved data. The gameplay scene
advances cloud drift on its fixed simulation step, so cloud speed is independent
of render frame rate. Camera offsets apply each cloud's small parallax factor.

Tune `BackgroundConfig` in `src/background.py` to change sky colors, cloud count,
drift range, parallax range, opacity, or the deterministic layout seed. Cloud
surfaces are built once when the renderer is created and reused while drawing.
