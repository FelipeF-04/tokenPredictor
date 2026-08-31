import argparse
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = ROOT / "extension"


def check_javascript():
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required for extension syntax checks.")

    javascript_files = sorted(EXTENSION_ROOT.rglob("*.js"))
    for path in javascript_files:
        completed = subprocess.run(
            [node, "--check", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            print(completed.stdout, end="")
            print(completed.stderr, end="")
            raise SystemExit(completed.returncode)
    print(f"JavaScript syntax valid: {len(javascript_files)} files")


def check_manifest():
    manifest_path = EXTENSION_ROOT / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid extension manifest JSON: {exc}") from exc

    if manifest.get("manifest_version") != 3:
        raise SystemExit("Extension manifest must use Manifest V3.")
    if not isinstance(manifest.get("content_scripts"), list):
        raise SystemExit("Extension manifest must define content_scripts.")
    print("Manifest JSON valid: Manifest V3")


def main():
    parser = argparse.ArgumentParser(description="Validate the MV3 extension sources.")
    parser.add_argument("--javascript", action="store_true", help="check JavaScript syntax")
    parser.add_argument("--manifest", action="store_true", help="validate manifest JSON")
    arguments = parser.parse_args()
    run_all = not arguments.javascript and not arguments.manifest

    if run_all or arguments.javascript:
        check_javascript()
    if run_all or arguments.manifest:
        check_manifest()


if __name__ == "__main__":
    main()
