import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


OFFLINE_TEST_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
}


def run(command, env=None):
    print(f"\n> {' '.join(str(part) for part in command)}", flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main():
    test_env = os.environ.copy()
    test_env.update(OFFLINE_TEST_ENV)

    print("Backend test suite", flush=True)
    run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "backend/tests",
            "-t",
            "backend",
            "-p",
            "test_*.py",
        ],
        env=test_env,
    )

    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required to run the extension tests.")
    print("\nExtension test suite", flush=True)
    javascript_tests = sorted((ROOT / "extension" / "tests").glob("*.test.js"))
    run(
        [node, "--test", *(str(path.relative_to(ROOT)) for path in javascript_tests)],
        env=test_env,
    )

    print("\nExtension compatibility checks", flush=True)
    run([sys.executable, "-B", "scripts/check_extension.py"], env=test_env)

    print("\nComplete offline test and compatibility suite passed.")


if __name__ == "__main__":
    main()
