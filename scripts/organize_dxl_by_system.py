from __future__ import annotations

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SOURCE_DIR = (
    REPO_ROOT / "main" / "1_target_dxl" / "Fm_Document_5" / "保守DB_1" / "output_DXL"
)
DEFAULT_DESTINATION_DIR = REPO_ROOT / "main" / "1_target_dxl" / "Fm_Document_5"
DXL_NS_URI = "http://www.lotus.com/dxl"
DXL_ITEM_TAG = f"{{{DXL_NS_URI}}}item"
INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
FALLBACK_DIR_NAME = "_NO_SYSTEM"


def sanitize_folder_name(value: str) -> str:
    cleaned = INVALID_FOLDER_CHARS.sub("_", value.strip())
    cleaned = cleaned.rstrip(" .")
    return cleaned or FALLBACK_DIR_NAME


def local_tag(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def extract_system_value_from_stream(stream: BytesIO, label: str) -> str | None:
    try:
        context = ET.iterparse(stream, events=("end",))
        for _, elem in context:
            if elem.tag != DXL_ITEM_TAG and local_tag(elem.tag) != "item":
                continue

            if elem.get("name") != "System":
                elem.clear()
                continue

            for child in elem:
                if local_tag(child.tag) == "text":
                    value = (child.text or "").strip()
                    elem.clear()
                    return value or None

            elem.clear()
            return None
    except ET.ParseError as exc:
        raise ValueError(f"DXL parse error: {label}") from exc

    return None


def extract_system_value(dxl_path: Path) -> str | None:
    with dxl_path.open("rb") as fh:
        return extract_system_value_from_stream(BytesIO(fh.read()), str(dxl_path))


def destination_path_for(destination_root: Path, system_value: str | None, filename: str) -> Path:
    folder_name = sanitize_folder_name(system_value or FALLBACK_DIR_NAME)
    return destination_root / folder_name / filename


def move_dxl_files(source_dir: Path, destination_root: Path, dry_run: bool) -> tuple[int, int, int]:
    moved = 0
    skipped = 0
    errors = 0

    for dxl_path in sorted(source_dir.rglob("*.dxl")):
        try:
            system_value = extract_system_value(dxl_path)
            destination_path = destination_path_for(destination_root, system_value, dxl_path.name)

            if destination_path.exists():
                print(f"[SKIP] already exists: {destination_path}")
                skipped += 1
                continue

            print(f"[MOVE] {dxl_path} -> {destination_path}")
            if not dry_run:
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dxl_path), str(destination_path))
            moved += 1
        except Exception as exc:
            print(f"[ERROR] {dxl_path}: {exc}")
            errors += 1

    return moved, skipped, errors


def extract_dxl_files_from_zip(source_zip: Path, destination_root: Path, dry_run: bool) -> tuple[int, int, int]:
    written = 0
    skipped = 0
    errors = 0

    with zipfile.ZipFile(source_zip) as zf:
        for info in sorted(zf.infolist(), key=lambda item: item.filename):
            if info.is_dir() or not info.filename.lower().endswith(".dxl"):
                continue

            filename = Path(info.filename).name
            try:
                raw = zf.read(info)
                system_value = extract_system_value_from_stream(BytesIO(raw), info.filename)
                destination_path = destination_path_for(destination_root, system_value, filename)

                if destination_path.exists():
                    print(f"[SKIP] already exists: {destination_path}")
                    skipped += 1
                    continue

                print(f"[EXTRACT] {info.filename} -> {destination_path}")
                if not dry_run:
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    destination_path.write_bytes(raw)
                written += 1
            except Exception as exc:
                print(f"[ERROR] {info.filename}: {exc}")
                errors += 1

    return written, skipped, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize DXL files into subfolders based on the <item name='System'> value."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Folder containing DXL files. Default: {DEFAULT_SOURCE_DIR}",
    )
    parser.add_argument(
        "--source-zip",
        type=Path,
        help="ZIP file containing DXL files. If specified, this is used instead of --source-dir.",
    )
    parser.add_argument(
        "--destination-dir",
        type=Path,
        default=DEFAULT_DESTINATION_DIR,
        help=f"Destination root folder for organized files. Default: {DEFAULT_DESTINATION_DIR}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without moving or extracting files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    destination_dir = args.destination_dir.resolve()

    if args.source_zip is not None:
        source_zip = args.source_zip.resolve()
        if not source_zip.exists() or not source_zip.is_file():
            raise SystemExit(f"source zip not found: {source_zip}")

        moved, skipped, errors = extract_dxl_files_from_zip(
            source_zip=source_zip,
            destination_root=destination_dir,
            dry_run=args.dry_run,
        )
        print(
            f"[DONE] source_zip={source_zip} destination_dir={destination_dir} dry_run={args.dry_run} "
            f"written={moved} skipped={skipped} errors={errors}"
        )
        return

    source_dir = args.source_dir.resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"source directory not found: {source_dir}")

    moved, skipped, errors = move_dxl_files(
        source_dir=source_dir,
        destination_root=destination_dir,
        dry_run=args.dry_run,
    )
    print(
        f"[DONE] source_dir={source_dir} destination_dir={destination_dir} dry_run={args.dry_run} "
        f"moved={moved} skipped={skipped} errors={errors}"
    )


if __name__ == "__main__":
    main()
