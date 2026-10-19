# Extracted gameplay evidence

These are analysis-only images derived from `../growtopia_gameplay.mp4`. They are not production game assets. No gameplay code is used to generate them.

## Timestamp rules

- `overview_01.jpg` and `overview_02.jpg`: source frames every five seconds, read left to right, then top to bottom.
- `coverage_01.jpg` through `coverage_09.jpg`: source frames every second, same reading order. The final sheet includes 02:20 and blank unused cells.
- Overview/coverage timestamps are original source PTS. Frames are selected by decoded index rather than an `fps` filter, to avoid labeling a nearby resampled frame as the nominal interval.
- Close-up sheets show an offset plus local PTS. Add them: `84s + 00:00:01.200` is 01:25.200.
- `detail_*.jpg`: native 1280 x 720 images without added labels; [detail_manifest.json](detail_manifest.json) maps filename to decoded time and frame index.
- `ui_NNN.jpg`: native UI stills; [ui_manifest.json](ui_manifest.json) records verified source PTS/frame index and exact re-encoding validation for these original stills. A filename like `ui_118.jpg` is 118 seconds = 01:58.
- `ui_detail_*.jpg`: additional native UI stills, sought/checked using the same OpenCV timestamp method but not listed in `ui_manifest.json`. For example, `ui_detail_078.00.jpg` is 78 seconds = 01:18.
- `ui_harvest.jpg`, `ui_seed.jpg`, `ui_reject.jpg`: supplementary collages labeled with **absolute source seconds**, sampled every 0.5 seconds. Their ranges are 01:20-01:27.500, 02:00-02:06.500 and 02:07-02:12.500 respectively. They do not use the offset-plus-local-PTS notation.
- `implementation_menu.png` and `implementation_gameplay.png`: baseline renders of the unchanged Python game with SDL dummy drivers. Gameplay uses random seed 0, a newly generated world, and a synthetic profile in scratch storage; no user save data was loaded or modified. These are not frames from the recording.

The 60 fps recording contains 8,434 frames. The original content's black padding/device bar remain in native stills. JPEG compression differs between extraction batches; different file sizes do not imply different source times.

## Evidence map

| File(s) | Source interval | Sampling |
| --- | --- | --- |
| [overview 1](overview_01.jpg), [overview 2](overview_02.jpg) | 00:00-02:20 | 5 seconds |
| [coverage 1](coverage_01.jpg) | 00:00-00:15 | 1 second |
| [coverage 2](coverage_02.jpg) | 00:16-00:31 | 1 second |
| [coverage 3](coverage_03.jpg) | 00:32-00:47 | 1 second |
| [coverage 4](coverage_04.jpg) | 00:48-01:03 | 1 second |
| [coverage 5](coverage_05.jpg) | 01:04-01:19 | 1 second |
| [coverage 6](coverage_06.jpg) | 01:20-01:35 | 1 second |
| [coverage 7](coverage_07.jpg) | 01:36-01:51 | 1 second |
| [coverage 8](coverage_08.jpg) | 01:52-02:07 | 1 second |
| [coverage 9](coverage_09.jpg) | 02:08-02:20 | 1 second |
| [jump 1](jump_01.jpg), [jump 2](jump_02.jpg) | 00:05.000-00:07.900 | 0.1 seconds |
| [punch 1](punch_01.jpg), [punch 2](punch_02.jpg) | 00:23.800-00:24.750 | 0.05 seconds |
| [dig 1](dig_01.jpg), [dig 2](dig_02.jpg) | 00:48.000-00:53.750 | 0.25 seconds |
| [placement](placement_01.jpg) | 01:24.000-01:26.800 | 0.2 seconds |
| [relocation 1](relocation_01.jpg), [relocation 2](relocation_02.jpg) | 01:32.000-01:33.900 | 0.1 seconds |
| [inventory](ui_detail_078.00.jpg) | 01:18.000 | Native still |
| [harvest](ui_detail_081.00.jpg) | 01:21.000 | Native still |
| [layered digging](detail_065.000.jpg) | 01:05.000 | Native still |
| [planting](ui_detail_121.00.jpg), [notice](ui_detail_121.25.jpg) | 02:01.000, 02:01.250 | Native stills |
| [splice rejection](ui_detail_129.00.jpg), [target rejection](detail_131.000.jpg) | 02:09.000, 02:11.000 | Native stills |
| [final frame](detail_140.550.jpg) | 02:20.550 | Native still |

## Reproducing the FFmpeg extraction

Run from the workspace root in PowerShell. Outputs shown here already exist; use another output name or choose explicitly whether to overwrite. `drawtext` uses Windows Arial only for analysis timestamp labels.

```powershell
ffprobe -v error -show_format -show_streams -of json references/growtopia_gameplay.mp4

ffmpeg -hide_banner -loglevel error -i references/growtopia_gameplay.mp4 -vf "select='not(mod(n,300))',scale=384:-1,drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='%{pts\:hms}':fontsize=20:fontcolor=white:box=1:boxcolor=black@0.8:x=6:y=6,tile=5x3" -fps_mode vfr references/analysis_frames/overview_%02d.jpg

ffmpeg -hide_banner -loglevel error -i references/growtopia_gameplay.mp4 -vf "select='not(mod(n,60))',scale=480:-1,drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='%{pts\:hms}':fontsize=20:fontcolor=white:box=1:boxcolor=black@0.8:x=6:y=6,tile=4x4" -fps_mode vfr references/analysis_frames/coverage_%02d.jpg

ffmpeg -hide_banner -loglevel error -ss 23.8 -i references/growtopia_gameplay.mp4 -t 1 -vf "select='not(mod(n,3))',scale=384:-1,drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='23.8s + %{pts\:hms}':fontsize=16:fontcolor=white:box=1:boxcolor=black@0.8:x=6:y=6,tile=5x2" -fps_mode vfr references/analysis_frames/punch_%02d.jpg
```

The other detail sheets use the same selection method with these settings:

| Prefix | Seek seconds | Duration seconds | Frame-index interval | Scale width | Tile layout |
| --- | --- | --- | --- | --- | --- |
| `jump_` | 5 | 3 | 6 | 480 | 5 x 3 |
| `dig_` | 48 | 6 | 15 | 480 | 4 x 3 |
| `placement_` | 84 | 3 | 12 | 384 | 5 x 3 |
| `relocation_` | 92 | 2 | 6 | 384 | 5 x 2 |

Native stills were obtained with OpenCV `VideoCapture`, seeking by milliseconds, decoding one frame, then checking `CAP_PROP_POS_MSEC` and `CAP_PROP_POS_FRAMES - 1`. Frame 4,680 is 01:18.000; frame 7,275 is 02:01.250. Source metadata is retained in [video_metadata.json](video_metadata.json).
