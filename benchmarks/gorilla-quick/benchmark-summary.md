# Staqtapp 1X Gorilla Benchmark Summary

- Version: `1.4.9`
- Profile: `quick`
- Passed cases: **27 / 27**
- Total measured case time: **3.826 s**
- Report SHA-256: `9db4ed30e495ff13a04eefa8f94e5348c300bd37fe0b5a68a57da33ac143e93c`

| Suite | Case | OK | Latency ms | Ops/s | Failures |
|---|---|---:|---:|---:|---:|
| write | addvar_64B | True | 65.035 | 92.26 | 0 |
| write | addvar_1024B | True | 61.637 | 97.34 | 0 |
| write | addvar_65536B | True | 164.819 | 36.40 | 0 |
| transaction | transaction_1 | True | 5.239 | 190.89 | 0 |
| transaction | individual_1 | True | 9.714 | 102.95 | 0 |
| transaction | transaction_10 | True | 5.548 | 1802.61 | 0 |
| transaction | individual_10 | True | 98.445 | 101.58 | 0 |
| transaction | transaction_100 | True | 6.566 | 15230.63 | 0 |
| transaction | individual_100 | True | 1415.198 | 70.66 | 0 |
| scale | build_100 | True | 17.765 | 5629.03 | 0 |
| scale | find_100 | True | 4.295 | 2328.38 | 0 |
| scale | load_100 | True | 2.531 | 3951.51 | 0 |
| scale | list_100 | True | 1.657 | 6036.42 | 0 |
| scale | integrity_100 | True | 7.712 | 259.33 | 0 |
| scale | build_1000 | True | 73.505 | 13604.54 | 0 |
| scale | find_1000 | True | 9.249 | 1081.14 | 0 |
| scale | load_1000 | True | 1.812 | 5519.28 | 0 |
| scale | list_1000 | True | 2.608 | 3834.74 | 0 |
| scale | integrity_1000 | True | 38.321 | 52.19 | 0 |
| typed | write_10 | True | 9.017 | 110.91 | 0 |
| typed | read_10 | True | 1.727 | 579.15 | 0 |
| typed | write_1000 | True | 42.403 | 23.58 | 0 |
| typed | read_1000 | True | 32.931 | 30.37 | 0 |
| corruption | repair_0 | True | 35.701 | 28.01 | 0 |
| corruption | repair_1 | True | 17.502 | 57.14 | 0 |
| corruption | repair_2 | True | 15.875 | 62.99 | 0 |
| non_halting | contained_failure_loop | True | 1679.241 | 119.10 | 0 |
