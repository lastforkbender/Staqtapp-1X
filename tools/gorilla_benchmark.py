from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import staqtapp

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None


@dataclass(slots=True)
class Sample:
    suite: str
    case: str
    operations: int
    payload_bytes: int
    elapsed_ns: int
    ok: bool
    failures: int = 0
    notes: str = ""

    @property
    def ops_per_second(self) -> float:
        return 0.0 if self.elapsed_ns <= 0 else self.operations / (self.elapsed_ns / 1e9)

    @property
    def latency_ms(self) -> float:
        return self.elapsed_ns / 1e6

    def as_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["latency_ms"] = self.latency_ms
        record["ops_per_second"] = self.ops_per_second
        return record


def _timed(call: Callable[[], Any]) -> tuple[Any, int]:
    started = time.perf_counter_ns()
    result = call()
    return result, time.perf_counter_ns() - started


def _is_ok(value: Any) -> bool:
    if isinstance(value, dict) and "ok" in value:
        return bool(value["ok"])
    if hasattr(value, "ok"):
        return bool(value)
    return not isinstance(value, staqtapp.CallFailure)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _rss_peak_bytes() -> int | None:
    if resource is None:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value * (1024 if sys.platform != "darwin" else 1))


def _new_vfs(root: Path, name: str) -> Path:
    staqtapp.configure(storage_dir=str(root), json_backend="auto")
    result = staqtapp.makevfs(name, "Gorilla", "Bench")
    if not _is_ok(result):
        raise RuntimeError(f"makevfs failed: {result!r}")
    return Path(staqtapp.listfiles()["vfs_file"])


def write_suite(root: Path, payload_sizes: Iterable[int], repeats: int) -> list[Sample]:
    samples: list[Sample] = []
    for size in payload_sizes:
        path = _new_vfs(root, f"write_{size}")
        payload = "x" * size
        latencies: list[int] = []
        failures = 0
        for index in range(repeats):
            result, elapsed = _timed(lambda i=index: staqtapp.addvar(f"v{i}", payload))
            latencies.append(elapsed)
            failures += int(not _is_ok(result))
        samples.append(Sample("write", f"addvar_{size}B", repeats, size * repeats, sum(latencies), failures == 0, failures,
                              f"p50_ms={statistics.median(latencies)/1e6:.6f};p95_ms={_percentile([v/1e6 for v in latencies], .95):.6f};vfs_bytes={path.stat().st_size}"))
    return samples


def transaction_suite(root: Path, operation_counts: Iterable[int], payload_size: int) -> list[Sample]:
    samples: list[Sample] = []
    payload = "t" * payload_size
    for count in operation_counts:
        _new_vfs(root, f"tx_{count}")
        calls = [("addvar", (f"v{i}", payload)) for i in range(count)]
        result, elapsed = _timed(lambda: staqtapp.run_transaction(calls))
        samples.append(Sample("transaction", f"transaction_{count}", count, count * payload_size, elapsed, bool(result), 0 if result else 1))

        _new_vfs(root, f"individual_{count}")
        started = time.perf_counter_ns()
        failures = 0
        for i in range(count):
            failures += int(not _is_ok(staqtapp.addvar(f"v{i}", payload)))
        individual_elapsed = time.perf_counter_ns() - started
        samples.append(Sample("transaction", f"individual_{count}", count, count * payload_size, individual_elapsed, failures == 0, failures))
    return samples


def variable_count_suite(root: Path, counts: Iterable[int]) -> list[Sample]:
    samples: list[Sample] = []
    for count in counts:
        path = _new_vfs(root, f"count_{count}")
        names = [f"v{i:08d}" for i in range(count)]
        values = [f"value-{i}" for i in range(count)]
        result, build_elapsed = _timed(lambda: staqtapp.appvar(names, values, None))
        samples.append(Sample("scale", f"build_{count}", count, sum(map(len, values)), build_elapsed, _is_ok(result), 0 if _is_ok(result) else 1,
                              f"vfs_bytes={path.stat().st_size}"))
        target = names[-1]
        for case, call in (
            ("find", lambda: staqtapp.findvar(target)),
            ("load", lambda: staqtapp.loadvar(False, target, "s")),
            ("list", staqtapp.listvars),
            ("integrity", lambda: staqtapp.verify_integrity(deep=True)),
        ):
            values_ns = []
            failures = 0
            repeats = 10 if case != "integrity" else 2
            for _ in range(repeats):
                response, elapsed = _timed(call)
                values_ns.append(elapsed)
                failures += int(not _is_ok(response))
            samples.append(Sample("scale", f"{case}_{count}", repeats, 0, sum(values_ns), failures == 0, failures,
                                  f"median_ms={statistics.median(values_ns)/1e6:.6f}"))
    return samples


def typed_suite(root: Path, item_counts: Iterable[int]) -> list[Sample]:
    samples: list[Sample] = []
    for count in item_counts:
        _new_vfs(root, f"typed_{count}")
        value = {
            "records": [(i, complex(i / 3.0, -i / 7.0), bytes([i % 251]) * 8) for i in range(count)],
            "flags": frozenset({True, False}),
            "label": "gorilla-Δ",
        }
        result, write_elapsed = _timed(lambda: staqtapp.set_value("typed", value))
        samples.append(Sample("typed", f"write_{count}", 1, count * 32, write_elapsed, _is_ok(result), 0 if _is_ok(result) else 1))
        restored, read_elapsed = _timed(lambda: staqtapp.get_value("typed"))
        exact = _is_ok(restored) and restored == value
        samples.append(Sample("typed", f"read_{count}", 1, count * 32, read_elapsed, exact, 0 if exact else 1))
    return samples


def corruption_suite(root: Path, iterations: int, seed: int) -> list[Sample]:
    samples: list[Sample] = []
    randomizer = random.Random(seed)
    for index in range(iterations):
        path = _new_vfs(root, f"corrupt_{index}")
        payload = "recover-me-" + ("z" * 128)
        staqtapp.addvar("target", payload)
        clean = path.read_bytes()
        map_path = path.with_suffix(path.suffix + ".integrity.json")
        document = json.loads(map_path.read_text(encoding="utf-8"))
        payload_regions = [r for r in document["regions"] if r.get("kind") == "payload" and r.get("name") == "target"]
        if not payload_regions:
            samples.append(Sample("corruption", f"repair_{index}", 1, len(clean), 0, False, 1, "payload region unavailable"))
            continue
        region = payload_regions[0]
        offset = randomizer.randrange(region["start"], region["end"])
        damaged = bytearray(clean)
        damaged[offset] ^= 0x01
        path.write_bytes(damaged)
        started = time.perf_counter_ns()
        detected = not _is_ok(staqtapp.verify_integrity())
        repaired = staqtapp.repair_vfs()
        elapsed = time.perf_counter_ns() - started
        exact = _is_ok(repaired) and path.read_bytes() == clean and _is_ok(staqtapp.verify_integrity())
        samples.append(Sample("corruption", f"repair_{index}", 1, len(clean), elapsed, detected and exact, 0 if detected and exact else 1))
    return samples


def non_halting_suite(root: Path, iterations: int) -> list[Sample]:
    _new_vfs(root, "non_halting")
    staqtapp.addvar("stable", "yes")
    failures = 0
    started = time.perf_counter_ns()
    for i in range(iterations):
        bad = staqtapp.addvar("stable", f"duplicate-{i}")
        good = staqtapp.changevar("stable", f"yes-{i}")
        failures += int(bool(bad) or not _is_ok(good))
    elapsed = time.perf_counter_ns() - started
    final = staqtapp.loadvar(False, "stable", "s")
    ok = failures == 0 and _is_ok(final)
    return [Sample("non_halting", "contained_failure_loop", iterations * 2, 0, elapsed, ok, failures)]


def summarize(samples: list[Sample]) -> dict[str, Any]:
    records = [sample.as_record() for sample in samples]
    failed = [record for record in records if not record["ok"]]
    return {
        "samples": len(records),
        "passed": len(records) - len(failed),
        "failed": len(failed),
        "total_elapsed_seconds": sum(record["elapsed_ns"] for record in records) / 1e9,
        "failures": [{"suite": r["suite"], "case": r["case"], "notes": r["notes"]} for r in failed],
    }


def run(profile: str = "quick", seed: int = 149) -> dict[str, Any]:
    profiles = {
        "quick": {"payloads": [64, 1024, 65536], "repeats": 6, "tx": [1, 10, 100], "counts": [100, 1000], "typed": [10, 1000], "corrupt": 3, "non_halting": 100},
        "standard": {"payloads": [64, 1024, 65536, 1048576], "repeats": 8, "tx": [1, 10, 100, 250], "counts": [1000, 5000], "typed": [1000, 5000], "corrupt": 10, "non_halting": 250},
    }
    if profile not in profiles:
        raise ValueError(f"unknown profile: {profile}")
    config = profiles[profile]
    with tempfile.TemporaryDirectory(prefix="staqtapp-gorilla-") as td:
        root = Path(td)
        samples: list[Sample] = []
        samples += write_suite(root, config["payloads"], config["repeats"])
        samples += transaction_suite(root, config["tx"], 128)
        samples += variable_count_suite(root, config["counts"])
        samples += typed_suite(root, config["typed"])
        samples += corruption_suite(root, config["corrupt"], seed)
        samples += non_halting_suite(root, config["non_halting"])
        report = {
            "schema": "staqtapp-gorilla-v1",
            "staqtapp_version": staqtapp.__version__,
            "profile": profile,
            "seed": seed,
            "generated_at_ns": time.time_ns(),
            "environment": {
                "python": sys.version,
                "implementation": platform.python_implementation(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
                "json_backend": staqtapp.json_backend_info(),
                "peak_rss_bytes": _rss_peak_bytes(),
            },
            "summary": summarize(samples),
            "results": [sample.as_record() for sample in samples],
        }
        canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
        return report


def write_outputs(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "benchmark-results.json"
    csv_path = output_dir / "benchmark-results.csv"
    md_path = output_dir / "benchmark-summary.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = report["results"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader(); writer.writerows(rows)
    summary = report["summary"]
    lines = [
        "# Staqtapp 1X Gorilla Benchmark Summary",
        "",
        f"- Version: `{report['staqtapp_version']}`",
        f"- Profile: `{report['profile']}`",
        f"- Passed cases: **{summary['passed']} / {summary['samples']}**",
        f"- Total measured case time: **{summary['total_elapsed_seconds']:.3f} s**",
        f"- Report SHA-256: `{report['report_sha256']}`",
        "",
        "| Suite | Case | OK | Latency ms | Ops/s | Failures |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['suite']} | {row['case']} | {row['ok']} | {row['latency_ms']:.3f} | {row['ops_per_second']:.2f} | {row['failures']} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reproducible Staqtapp 1X hostile-scale benchmark harness")
    parser.add_argument("--profile", choices=("quick", "standard"), default="quick")
    parser.add_argument("--seed", type=int, default=149)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-output"))
    args = parser.parse_args(argv)
    report = run(args.profile, args.seed)
    write_outputs(report, args.output_dir)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
