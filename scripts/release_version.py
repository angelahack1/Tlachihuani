"""Resolve release tags numerically and stamp only product-owned version fields."""
import argparse
import json
import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

TAG = re.compile(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def latest_tag(tags):
    candidates = [(tuple(map(int, m.groups())), tag) for tag in tags if (m := TAG.fullmatch(tag))]
    if not candidates:
        raise ValueError("No stable release tag found. Expected vX.Y.Z (or X.Y.Z) in the local repository.")
    parts, tag = max(candidates)
    if parts[0] > 255 or parts[1] > 255 or parts[2] > 65535:
        raise ValueError("Latest tag exceeds Windows Installer version limits: " + tag)
    return tag, ".".join(map(str, parts))


def stamp(root, version):
    # Prepare every edit before writing. External package pins/hashes are untouched.
    props = root / "Directory.Build.props"
    source = props.read_text(encoding="utf-8-sig")
    if len(ET.fromstring(source).findall(".//Version")) != 1:
        raise ValueError("Expected exactly one product Version in Directory.Build.props")
    edits = {props: re.sub(r"<Version>[^<]+</Version>", "<Version>" + version + "</Version>", source)}
    for base in (root / "src", root / "tests"):
        for path in base.rglob("packages.lock.json"):
            text = path.read_text(encoding="utf-8-sig")
            json.loads(text)
            text = re.sub(r'("Tlachihuani\.[^"]+"\s*:\s*")\[[0-9]+\.[0-9]+\.[0-9]+, \)(")',
                          lambda m: m[1] + "[" + version + ", )" + m[2], text)
            json.loads(text)
            edits[path] = text
    for path, text in edits.items():
        if path.read_text(encoding="utf-8-sig") != text:
            path.write_text(text, encoding="utf-8", newline="")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--stamp", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("Run against the Tlachihuani repository root.")
    tag, version = latest_tag(git(root, "tag", "--list").splitlines())
    ancestor = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", tag + "^{commit}", "HEAD"])
    if ancestor.returncode:
        raise ValueError("The latest tag is not an ancestor of this checkout: " + tag)
    record = {"tag": tag, "version": version, "commit": git(root, "rev-parse", "HEAD"),
              "working_tree_modified": bool(git(root, "status", "--porcelain"))}
    if args.stamp:
        stamp(root, version)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
