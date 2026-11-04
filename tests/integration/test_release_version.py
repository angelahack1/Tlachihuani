"""Release ordering and product stamping must not loosen dependency pins."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_version", ROOT / "scripts/release_version.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseVersionTests(unittest.TestCase):
    def test_numeric_order_and_prereleases(self):
        self.assertEqual(release.latest_tag(["v0.9.9", "v0.10.0", "v1.0.0-rc1", "notes"]), ("v0.10.0", "0.10.0"))
        self.assertEqual(release.latest_tag(["v0.2.1", "1.2.0"]), ("1.2.0", "1.2.0"))

    def test_new_tag_is_selected_on_every_call(self):
        tags = ["v0.2.0"]
        self.assertEqual(release.latest_tag(tags)[1], "0.2.0")
        tags.append("v0.2.1")
        self.assertEqual(release.latest_tag(tags)[1], "0.2.1")

    def test_missing_and_unsupported_versions_fail(self):
        for tags in ([], ["v1.2.3.4"], ["v01.2.3"], ["v256.0.0"], ["v1.256.0"], ["v1.0.65536"]):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                release.latest_tag(tags)

    def test_stamp_preserves_external_dependencies_and_is_repeatable(self):
        scratch = ROOT / "artifacts/verification/version-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory)
            (root / "src/Example").mkdir(parents=True)
            (root / "Directory.Build.props").write_text("<Project><PropertyGroup><Version>0.1.0</Version></PropertyGroup></Project>")
            lock = root / "src/Example/packages.lock.json"
            lock.write_text(json.dumps({"dependencies": {"Tlachihuani.Core": "[0.1.0, )", "Microsoft.Extensions.Hosting": "[10.0.12, )", "contentHash": "unchanged"}}))
            release.stamp(root, "0.2.1")
            first = lock.read_bytes()
            release.stamp(root, "0.2.1")
            self.assertEqual(first, lock.read_bytes())
            deps = json.loads(first)["dependencies"]
            self.assertEqual(deps["Tlachihuani.Core"], "[0.2.1, )")
            self.assertEqual(deps["Microsoft.Extensions.Hosting"], "[10.0.12, )")
            self.assertEqual(deps["contentHash"], "unchanged")
            self.assertIn("<Version>0.2.1</Version>", (root / "Directory.Build.props").read_text())


if __name__ == "__main__":
    unittest.main()
