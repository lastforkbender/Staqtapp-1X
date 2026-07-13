# Staqtapp 1X Gorilla Benchmark Summary

- Version: `1.4.9`
- Profile: `standard`
- Passed cases: **37 / 37**
- Total measured case time: **14.413 s**
- Report SHA-256: `1b4602edad95acf02d606b8b9ff339e641055e5fcc362223444ef22e8db34b1b`

| Suite | Case | OK | Latency ms | Ops/s | Failures |
|---|---|---:|---:|---:|---:|
| write | addvar_64B | True | 84.116 | 95.11 | 0 |
| write | addvar_1024B | True | 76.042 | 105.21 | 0 |
| write | addvar_65536B | True | 252.116 | 31.73 | 0 |
| write | addvar_1048576B | True | 2138.812 | 3.74 | 0 |
| transaction | transaction_1 | True | 6.902 | 144.90 | 0 |
| transaction | individual_1 | True | 8.876 | 112.66 | 0 |
| transaction | transaction_10 | True | 5.831 | 1714.87 | 0 |
| transaction | individual_10 | True | 96.651 | 103.47 | 0 |
| transaction | transaction_100 | True | 7.790 | 12837.51 | 0 |
| transaction | individual_100 | True | 1377.825 | 72.58 | 0 |
| transaction | transaction_250 | True | 13.534 | 18472.00 | 0 |
| transaction | individual_250 | True | 4651.846 | 53.74 | 0 |
| scale | build_1000 | True | 37.542 | 26636.56 | 0 |
| scale | find_1000 | True | 7.611 | 1313.92 | 0 |
| scale | load_1000 | True | 1.712 | 5839.43 | 0 |
| scale | list_1000 | True | 2.706 | 3695.39 | 0 |
| scale | integrity_1000 | True | 36.202 | 55.25 | 0 |
| scale | build_5000 | True | 171.846 | 29095.80 | 0 |
| scale | find_5000 | True | 30.796 | 324.71 | 0 |
| scale | load_5000 | True | 2.134 | 4686.81 | 0 |
| scale | list_5000 | True | 2.615 | 3824.71 | 0 |
| scale | integrity_5000 | True | 237.553 | 8.42 | 0 |
| typed | write_1000 | True | 51.626 | 19.37 | 0 |
| typed | read_1000 | True | 26.785 | 37.33 | 0 |
| typed | write_5000 | True | 161.962 | 6.17 | 0 |
| typed | read_5000 | True | 147.343 | 6.79 | 0 |
| corruption | repair_0 | True | 15.084 | 66.29 | 0 |
| corruption | repair_1 | True | 17.307 | 57.78 | 0 |
| corruption | repair_2 | True | 14.853 | 67.32 | 0 |
| corruption | repair_3 | True | 14.735 | 67.87 | 0 |
| corruption | repair_4 | True | 16.862 | 59.30 | 0 |
| corruption | repair_5 | True | 17.638 | 56.70 | 0 |
| corruption | repair_6 | True | 17.792 | 56.21 | 0 |
| corruption | repair_7 | True | 17.212 | 58.10 | 0 |
| corruption | repair_8 | True | 18.868 | 53.00 | 0 |
| corruption | repair_9 | True | 15.855 | 63.07 | 0 |
| non_halting | contained_failure_loop | True | 4608.011 | 108.51 | 0 |
