# Staqtapp 1X Gorilla Benchmark Summary

- Version: `1.5.0`
- Profile: `quick`
- Passed cases: **27 / 27**
- Total measured case time: **3.436 s**
- Report SHA-256: `59f7d8c764b8948affcda71c38dde7474d11c249a65763f438f6750dff0b0c48`

| Suite | Case | OK | Latency ms | Ops/s | Failures |
|---|---|---:|---:|---:|---:|
| write | addvar_64B | True | 61.389 | 97.74 | 0 |
| write | addvar_1024B | True | 55.804 | 107.52 | 0 |
| write | addvar_65536B | True | 158.926 | 37.75 | 0 |
| transaction | transaction_1 | True | 6.750 | 148.15 | 0 |
| transaction | individual_1 | True | 9.094 | 109.97 | 0 |
| transaction | transaction_10 | True | 5.890 | 1697.87 | 0 |
| transaction | individual_10 | True | 95.732 | 104.46 | 0 |
| transaction | transaction_100 | True | 7.404 | 13506.09 | 0 |
| transaction | individual_100 | True | 1242.392 | 80.49 | 0 |
| scale | build_100 | True | 12.974 | 7707.57 | 0 |
| scale | find_100 | True | 4.690 | 2132.22 | 0 |
| scale | load_100 | True | 2.171 | 4607.13 | 0 |
| scale | list_100 | True | 2.398 | 4170.19 | 0 |
| scale | integrity_100 | True | 6.710 | 298.06 | 0 |
| scale | build_1000 | True | 56.121 | 17818.56 | 0 |
| scale | find_1000 | True | 8.603 | 1162.43 | 0 |
| scale | load_1000 | True | 1.782 | 5611.92 | 0 |
| scale | list_1000 | True | 1.272 | 7860.63 | 0 |
| scale | integrity_1000 | True | 36.643 | 54.58 | 0 |
| typed | write_10 | True | 12.440 | 80.38 | 0 |
| typed | read_10 | True | 1.908 | 524.03 | 0 |
| typed | write_1000 | True | 50.726 | 19.71 | 0 |
| typed | read_1000 | True | 30.742 | 32.53 | 0 |
| corruption | repair_0 | True | 14.879 | 67.21 | 0 |
| corruption | repair_1 | True | 14.639 | 68.31 | 0 |
| corruption | repair_2 | True | 14.974 | 66.78 | 0 |
| non_halting | contained_failure_loop | True | 1519.175 | 131.65 | 0 |
