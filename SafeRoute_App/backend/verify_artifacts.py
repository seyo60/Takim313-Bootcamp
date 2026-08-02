"""Fail-fast verification for immutable routing artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path


EXPECTED = {
    "compact_graph_res10.npz": "8fb2ef8aaaebc8a9502a043620223ff3dde97a774c9e35347f5681a953e89eb1",
    "compact_graph.npz": "df5a36deaff5bd0eb83f22a917f7f982883110e5ac7d072724cfcf9a7bbabdd8",
    "navigation_sidecar_res10.npz": "1ea385d6c06a0cebb94485a676c7b6907dd85fc59f17a099e70a00c1b34d8dee",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    data_dir = Path(__file__).resolve().parent.parent / "data-science"
    for name, expected in EXPECTED.items():
        path = data_dir / name
        if not path.is_file():
            raise SystemExit(f"Missing routing artifact: {path}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"Routing artifact checksum mismatch: {name}")
        print(f"verified {name} sha256:{actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
