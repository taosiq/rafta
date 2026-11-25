# Rafta policy experiment (simulation #2)

Holdout 2026-07-28 to 2026-11-24, 150 SKUs ({'A': 53, 'B': 44, 'C': 53}), 30 replications, common random numbers.

| Policy | Total cost | Holding | Ordering | Shortage | Fill rate | Stock-out SKU-days |
|---|---:|---:|---:|---:|---:|---:|
| Uniform 95% | 45,331 | 20,210 | 18,576 | 6,546 | 99.32% | 63.6 |
| ABC 98/95/90 | 44,285 | 20,826 | 18,596 | 4,863 | 99.44% | 54.9 |
| ABC-XYZ matrix | 44,038 | 21,325 | 18,591 | 4,123 | 99.50% | 47.2 |

| Candidate vs baseline | Cost diff (95% CI) | p | Stock-out days | Saving vs uniform frontier | Verdict |
|---|---|---:|---:|---:|---|
| ABC 98/95/90 vs Uniform 95% | -1,046 [-1,472, -621] | 2.34e-05 | -13.7% | 0.7% | **dominates** |
| ABC-XYZ matrix vs Uniform 95% | -1,293 [-1,800, -785] | 1.41e-05 | -25.7% | 0.3% | **dominates** |
