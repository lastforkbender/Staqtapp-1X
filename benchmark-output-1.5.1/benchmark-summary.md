# Staqtapp 1X Gorilla Benchmark Summary

- Version: `1.5.1`
- Profile: `quick`
- Passed cases: **27 / 27**
- Total measured case time: **3.616 s**
- Report SHA-256: `e49ed86f88c2e10eebc0339c600a6a4507bf0f7111dbdb170fa6d56010f7bbb2`

| Suite | Case | OK | Latency ms | Ops/s | Failures |
|---|---|---:|---:|---:|---:|
| write | addvar_64B | True | 83.878 | 71.53 | 0 |
| write | addvar_1024B | True | 56.827 | 105.58 | 0 |
| write | addvar_65536B | True | 137.540 | 43.62 | 0 |
| transaction | transaction_1 | True | 7.271 | 137.54 | 0 |
| transaction | individual_1 | True | 9.053 | 110.46 | 0 |
| transaction | transaction_10 | True | 8.883 | 1125.70 | 0 |
| transaction | individual_10 | True | 90.713 | 110.24 | 0 |
| transaction | transaction_100 | True | 7.540 | 13262.37 | 0 |
| transaction | individual_100 | True | 1372.149 | 72.88 | 0 |
| scale | build_100 | True | 17.163 | 5826.66 | 0 |
| scale | find_100 | True | 5.198 | 1923.80 | 0 |
| scale | load_100 | True | 2.162 | 4625.34 | 0 |
| scale | list_100 | True | 2.977 | 3359.51 | 0 |
| scale | integrity_100 | True | 7.637 | 261.87 | 0 |
| scale | build_1000 | True | 68.504 | 14597.63 | 0 |
| scale | find_1000 | True | 8.841 | 1131.09 | 0 |
| scale | load_1000 | True | 3.253 | 3073.88 | 0 |
| scale | list_1000 | True | 6.629 | 1508.48 | 0 |
| scale | integrity_1000 | True | 34.063 | 58.71 | 0 |
| typed | write_10 | True | 7.633 | 131.00 | 0 |
| typed | read_10 | True | 2.031 | 492.30 | 0 |
| typed | write_1000 | True | 47.729 | 20.95 | 0 |
| typed | read_1000 | True | 30.727 | 32.54 | 0 |
| corruption | repair_0 | True | 15.888 | 62.94 | 0 |
| corruption | repair_1 | True | 15.372 | 65.05 | 0 |
| corruption | repair_2 | True | 18.594 | 53.78 | 0 |
| non_halting | contained_failure_loop | True | 1547.636 | 129.23 | 0 |
