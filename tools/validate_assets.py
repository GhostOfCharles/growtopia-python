"""Check PNG alpha and dimensions in the game's asset tree."""

import argparse
import json
from pathlib import Path

import pygame


def validate(root):
    issues = []
    root = Path(root).resolve()
    pngs = sorted(Path(root).rglob("*.png"))
    if not pngs:
        print(f"No PNG files found under {root}")
        return 0
    for path in pngs:
        try:
            image = pygame.image.load(str(path))
        except (pygame.error, OSError) as error:
            issues.append(f"{path}: cannot load PNG ({error})")
            continue
        size = image.get_size()
        if min(size) <= 0:
            issues.append(f"{path}: invalid image dimensions {size}")
        if not image.get_flags() & pygame.SRCALPHA:
            relative_parts = path.relative_to(root).parts
            if relative_parts and relative_parts[0] == "blocks":
                print(f"NOTE {path}: opaque block texture/source; alpha is optional")
            else:
                issues.append(f"{path}: no per-pixel alpha channel")
        else:
            rgba = pygame.image.tobytes(image, "RGBA")
            if not any(rgba[index] == 0 for index in range(3, len(rgba), 4)):
                print(f"NOTE {path}: alpha channel exists but has no fully transparent pixels")
        print(f"OK   {path}: {size[0]}x{size[1]} px, alpha={'yes' if image.get_flags() & pygame.SRCALPHA else 'no'}")
    for config_path in root.rglob("animation.json"):
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            issues.append(f"{config_path}: invalid animation config ({error})")
            continue
        for state, entry in config.get("animations", {}).items():
            if "sheet" in entry:
                sheet_path = root / entry["sheet"]
                if not sheet_path.is_file():
                    print(f"NOTE {state}: sprite sheet is missing; procedural fallback will be used")
                    continue
                try:
                    image = pygame.image.load(str(sheet_path))
                    frame_width, frame_height = map(int, entry["frame_size"])
                except (pygame.error, OSError, KeyError, TypeError, ValueError) as error:
                    issues.append(f"{sheet_path}: invalid sheet configuration ({error})")
                    continue
                if frame_width <= 0 or frame_height <= 0 or image.get_width() % frame_width or image.get_height() % frame_height:
                    issues.append(f"{sheet_path}: dimensions {image.get_size()} do not fit frames {frame_width}x{frame_height}")
                    continue
                available = image.get_width() // frame_width * (image.get_height() // frame_height)
                count = entry.get("count", available)
                if not 0 < count <= available:
                    issues.append(f"{sheet_path}: configured frame count {count} exceeds {available}")
                if "durations_ms" in entry and len(entry["durations_ms"]) != count:
                    issues.append(f"{sheet_path}: duration count differs from frame count {count}")
            elif "frames" in entry:
                frame_paths = [root / item for item in entry["frames"]]
                present = [path for path in frame_paths if path.is_file()]
                if not present:
                    print(f"NOTE {state}: frames are missing; procedural fallback will be used")
                    continue
                dimensions = {pygame.image.load(str(path)).get_size() for path in present}
                if len(dimensions) != 1:
                    issues.append(f"{state}: frame dimensions differ: {sorted(dimensions)}")
                if "durations_ms" in entry and len(entry["durations_ms"]) != len(frame_paths):
                    issues.append(f"{state}: duration count differs from frame count {len(frame_paths)}")
    for issue in issues:
        print(f"ERROR {issue}")
    print(f"Checked {len(pngs)} PNG file(s); {len(issues)} issue(s)")
    return len(issues)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1] / "assets",
                        type=Path, help="asset directory (default: project assets/)")
    args = parser.parse_args()
    pygame.init()
    raise SystemExit(1 if validate(args.root) else 0)
