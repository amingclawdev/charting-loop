from pathlib import Path
import hashlib, json
root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
for record in manifest["files"]:
    path = root / record["path"]
    assert path.parent == root and path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], path.name
for line in (root / "SHA256SUMS").read_text().splitlines():
    expected, name = line.split("  ", 1)
    path = root / name
    assert path.parent == root and path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
records = json.loads((root / "records.json").read_text())
for excerpt in records["source_excerpts"]:
    assert hashlib.sha256(excerpt["redacted_excerpt"].encode()).hexdigest() == excerpt["excerpt_sha256"]
print("Bundle byte identities verified. This does not prove source truth or workflow certification.")
