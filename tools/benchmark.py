from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

import staqtapp


def elapsed(call, repeats=1):
    values=[]
    result=None
    for _ in range(repeats):
        start=time.perf_counter_ns(); result=call(); values.append(time.perf_counter_ns()-start)
    return result, values


def run(count: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="staqtapp-bench-") as td:
        staqtapp.configure(storage_dir=td)
        _, create_ns = elapsed(lambda: staqtapp.makevfs("bench", "BenchDir", "BenchFolder"))
        names=[f"v{i}" for i in range(count)]
        values=[f"value-{i}" for i in range(count)]
        _, batch_ns = elapsed(lambda: staqtapp.appvar(names, values, None))
        _, list_ns = elapsed(staqtapp.listvars, repeats=25)
        _, find_ns = elapsed(lambda: staqtapp.findvar(f"v{count-1}"), repeats=100)
        _, load_ns = elapsed(lambda: staqtapp.loadvar(False, f"v{count-1}", "s"), repeats=100)
        path=Path(staqtapp.listfiles()["vfs_file"])
        size_before=path.stat().st_size
        _, change_ns = elapsed(lambda: staqtapp.changevar(f"v{count//2}", "x"))
        size_after=path.stat().st_size
        return {
            "python": __import__("sys").version,
            "records": count,
            "vfs_bytes_before_change": size_before,
            "vfs_bytes_after_change": size_after,
            "create_ms": create_ns[0]/1e6,
            "batch_add_ms": batch_ns[0]/1e6,
            "listvars_median_ms": statistics.median(list_ns)/1e6,
            "findvar_median_ms": statistics.median(find_ns)/1e6,
            "loadvar_median_ms": statistics.median(load_ns)/1e6,
            "changevar_ms": change_ns[0]/1e6,
            "approx_change_write_amplification": size_after,
            "verification": staqtapp.verify_vfs(),
        }


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--records", type=int, default=2000); p.add_argument("--output", type=Path)
    a=p.parse_args(argv); report=run(a.records); text=json.dumps(report, indent=2)
    if a.output: a.output.write_text(text+"\n", encoding="utf-8")
    print(text)

if __name__ == "__main__": main()
