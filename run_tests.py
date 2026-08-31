from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def run(command):
    print(f"\n> {' '.join(str(part) for part in command)}", flush=True)
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main():
    run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "backend",
            "-p",
            "test_*.py",
        ]
    )

    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required to run the extension tests.")
    javascript_tests = sorted((ROOT / "extension" / "tests").glob("*.test.js"))
    run([node, "--test", *(str(path.relative_to(ROOT)) for path in javascript_tests)])

    print("\nComplete Python and JavaScript test suite passed.")


if __name__ == "__main__":
    main()
