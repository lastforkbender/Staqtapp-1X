from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import staqtapp


def _write_fixture(path: Path, count: int) -> None:
    folder = "BenchFolder"
    directory = "BenchDir"
    with path.open("wb") as stream:
        stream.write(b":\xe2\x98\x86Staqtapp-v1.4.0\n")
        stream.write(f"|:{directory}<{folder}>\n".encode())
        stream.write(f"_|:{folder}<sub-{folder}>\n".encode())
        stream.write(f"__|:sub-{folder}<tqpt-{folder},tpqt-{folder},null>\n".encode())
        stream.write(f"___|:tqpt-{folder}<tqpt,null,n>:\nnull\n".encode())
        for index in range(count):
            if index:
                stream.write(b"\n")
            stream.write(f"v{index}<@qp(value-{index}):>".encode())
        stream.write(f":\n___|:(tqpt-{folder})\n".encode())
        stream.write(f"___|:tpqt-{folder}<tpqt,null,n>:\nnull:\n".encode())
        stream.write(
            f"___|:(tpqt-{folder})\n__|:(sub-{folder})\n_|:({folder})\n|:({directory})".encode()
        )


def _median_ms(call, repeats: int) -> float:
    values: list[int] = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        call()
        values.append(time.perf_counter_ns() - started)
    return statistics.median(values) / 1_000_000


def _fresh_process(root: Path, count: int) -> dict:
    staqtapp.configure(storage_dir=root)
    started = time.perf_counter_ns()
    staqtapp.setpath("bench", "BenchDir", "BenchFolder")
    reopen_ms = (time.perf_counter_ns() - started) / 1_000_000
    started = time.perf_counter_ns()
    found = staqtapp.findvar(f"v{count - 1}")
    first_lookup_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {"reopen_ms": reopen_ms, "first_lookup_ms": first_lookup_ms, "found": found}


def run(count: int) -> dict:
    repeats = max(5, min(100, 5_000_000 // count))
    with tempfile.TemporaryDirectory(prefix="staqtapp-large-read-") as directory:
        root = Path(directory)
        vfs_path = root / "bench.sqtpp"
        _write_fixture(vfs_path, count)
        staqtapp.configure(storage_dir=root)

        started = time.perf_counter_ns()
        staqtapp.setpath("bench", "BenchDir", "BenchFolder")
        first_open_ms = (time.perf_counter_ns() - started) / 1_000_000

        started = time.perf_counter_ns()
        found = staqtapp.findvar(f"v{count - 1}")
        first_lookup_ms = (time.perf_counter_ns() - started) / 1_000_000

        warm_find = _median_ms(lambda: staqtapp.findvar(f"v{count - 1}"), repeats)
        warm_load = _median_ms(lambda: staqtapp.loadvar(False, f"v{count - 1}", "s"), repeats)
        list_once = _median_ms(staqtapp.listvars, 1)
        index_path = vfs_path.with_suffix(".sqti")

        child_env = os.environ.copy()
        child = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child-root",
                str(root),
                "--records",
                str(count),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=child_env,
        )
        fresh = json.loads(child.stdout)
        return {
            "staqtapp": staqtapp.__version__,
            "python": sys.version,
            "records": count,
            "vfs_bytes": vfs_path.stat().st_size,
            "sidecar_bytes": index_path.stat().st_size,
            "first_index_build_ms": first_open_ms,
            "first_lookup_after_build_ms": first_lookup_ms,
            "warm_find_median_ms": warm_find,
            "warm_load_median_ms": warm_load,
            "listvars_once_ms": list_once,
            "fresh_process": fresh,
            "lookup_verified": found,
            "repeats": repeats,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark large Staqtapp mapped reads")
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child-root", type=Path)
    args = parser.parse_args(argv)
    if args.records < 1:
        parser.error("--records must be positive")
    if args.child_root is not None:
        print(json.dumps(_fresh_process(args.child_root, args.records)))
        return 0
    report = run(args.records)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
