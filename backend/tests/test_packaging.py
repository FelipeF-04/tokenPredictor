import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PACKAGER_PATH = ROOT / "scripts" / "package_extension.py"
SPEC = importlib.util.spec_from_file_location("package_extension", PACKAGER_PATH)
package_extension = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_extension)


class ExtensionPackagingTests(unittest.TestCase):
    def test_package_is_deterministic_and_excludes_development_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.zip"
            second_path = Path(temp_dir) / "second.zip"

            first = package_extension.create_package(first_path)
            second = package_extension.create_package(second_path)

            self.assertEqual(first["sha256"], second["sha256"])
            with zipfile.ZipFile(first_path) as archive:
                names = archive.namelist()

            self.assertIn("manifest.json", names)
            self.assertIn("background.js", names)
            self.assertIn("content.js", names)
            self.assertFalse(any(name.startswith("tests/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith(".zip") for name in names))


if __name__ == "__main__":
    unittest.main()
