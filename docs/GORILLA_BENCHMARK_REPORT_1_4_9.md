# Staqtapp 1X 1.4.9 Gorilla Benchmark Report

## Scope

The 1.4.9 harness stresses directly operational storage paths rather than synthetic codec functions alone. It measures durable writes, batched transactions, variable-count scaling, typed values, integrity verification, controlled payload corruption, surgical recovery, and repeated contained failures.

## Included profiles

- `quick`: CI and smoke validation.
- `standard`: stronger local baseline that remains practical on ordinary development hosts.

Larger endurance campaigns should run the same harness repeatedly under an external scheduler while archiving each result directory.

## Baseline outcome

The packaged standard run passed **37/37** cases with zero benchmark-classified failures.

Selected observations from this host:

- 250 operations in one transaction: approximately 13.5 ms.
- 250 individually durable calls: approximately 4.65 s.
- 5,000-variable batch construction: approximately 172 ms.
- 5,000-variable last-key lookup median: approximately 0.179 ms.
- deep integrity verification over the 5,000-variable fixture: approximately 119 ms median.
- all controlled payload corruptions were detected and exactly repaired.
- 250 repeated duplicate failures were contained while subsequent valid mutations continued.

The transaction comparison is intentionally end-to-end and includes Staqtapp durability, integrity-map, and revision behavior. It demonstrates why related writes should use `run_transaction()`.

## Trust rules

- A case is successful only when its returned result explicitly indicates success.
- Mapping results containing `"ok": false` are failures even though non-empty Python dictionaries are truthy.
- Corruption tests compare repaired VFS bytes with the exact pre-corruption image and then require deep integrity verification.
- Reports contain a SHA-256 over the canonical report body.
- Results record the Python, platform, processor, CPU count, JSON backend, seed, and peak resident memory where supported.

## Running

```bash
PYTHONPATH=src python tools/gorilla_benchmark.py \
  --profile standard \
  --seed 149 \
  --output-dir benchmark-output
```

Generated files:

- `benchmark-results.json`
- `benchmark-results.csv`
- `benchmark-summary.md`

## Limitations

The packaged baseline is not a 24-hour certification and does not claim one-million-variable support. Very large campaigns are hardware- and filesystem-dependent and should be run on the target deployment platform. The harness is designed so those runs can be reproduced without altering core storage code.
