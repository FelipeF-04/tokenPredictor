"""Create a deterministic, runtime-only ZIP of the Chrome extension."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = ROOT / "extension"
EXCLUDED_DIRECTORIES = {
    ".cache",
    "__pycache__",
    "coverage",
    "node_modules",
    "test-results",
    "tests",
}
EXCLUDED_NAMES = {
    ".DS_Store",
    ".env",
    "Thumbs.db",
    "config.local.json",
    "local.config.json",
}
EXCLUDED_SUFFIXES = {".log", ".map", ".pyc", ".pyo", ".zip"}


def should_package(relative_path):
    if any(part in EXCLUDED_DIRECTORIES for part in relative_path.parts[:-1]):
        return False
    name = relative_path.name
    if name in EXCLUDED_NAMES or name.startswith(".env."):
        return False
    return relative_path.suffix.lower() not in EXCLUDED_SUFFIXES


def package_files():
    return sorted(
        (
            path
            for path in EXTENSION_ROOT.rglob("*")
            if path.is_file() and should_package(path.relative_to(EXTENSION_ROOT))
        ),
        key=lambda path: path.relative_to(EXTENSION_ROOT).as_posix(),
    )


def manifest_runtime_files(manifest):
    required = {"manifest.json"}
    background = manifest.get("background") or {}
    if background.get("service_worker"):
        required.add(background["service_worker"])
    action = manifest.get("action") or {}
    if action.get("default_popup"):
        required.add(action["default_popup"])
    for entry in manifest.get("content_scripts") or []:
        required.update(entry.get("js") or [])
        required.update(entry.get("css") or [])
    return required


def create_package(output_path):
    manifest_path = EXTENSION_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3:
        raise ValueError("extension/manifest.json must be Manifest V3")

    destination = Path(output_path).resolve()
    try:
        destination.relative_to(EXTENSION_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("package output must be outside the extension source directory")

    destination.parent.mkdir(parents=True, exist_ok=True)
    files = package_files()
    if manifest_path not in files:
        raise ValueError("extension manifest was excluded from the package")
    archive_names = {
        path.relative_to(EXTENSION_ROOT).as_posix() for path in files
    }
    missing_runtime_files = sorted(manifest_runtime_files(manifest) - archive_names)
    if missing_runtime_files:
        raise ValueError(
            "manifest references files missing from package: "
            + ", ".join(missing_runtime_files)
        )

    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="ai-usage-extension-",
            suffix=".zip",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = Path(temporary.name)

        with zipfile.ZipFile(
            temporary_name,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for source_path in files:
                relative_path = source_path.relative_to(EXTENSION_ROOT).as_posix()
                info = zipfile.ZipInfo(relative_path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, source_path.read_bytes())

        os.replace(temporary_name, destination)
    finally:
        if temporary_name and temporary_name.exists():
            temporary_name.unlink()

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return {
        "path": destination,
        "file_count": len(files),
        "sha256": digest,
        "version": manifest.get("version", "unknown"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="ZIP destination (default: dist/ai-usage-predictor-<version>.zip)",
    )
    arguments = parser.parse_args()
    manifest = json.loads(
        (EXTENSION_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    output_path = arguments.output or (
        ROOT / "dist" / f"ai-usage-predictor-{manifest.get('version', 'unknown')}.zip"
    )
    result = create_package(output_path)
    print(
        f"Created {result['path']} ({result['file_count']} files, "
        f"version {result['version']})"
    )
    print(f"SHA-256: {result['sha256']}")


if __name__ == "__main__":
    main()
