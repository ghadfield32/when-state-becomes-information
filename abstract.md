## When State Becomes Information: Release-Conditioned Basketball Forecasting

**Introduction.** Teams have little public evidence on when finger-level motion capture improves prediction. We ask whether richer body and hand state improves a 100 ms ball forecast, and whether that depends on timing within the shot.

**Methods.** We used SPL Open Data free-throw motion capture (MLSE Sport Performance Lab, CC BY-NC-SA 4.0) from three athletes at 60 Hz. There were 9,619 forecast decisions, one every 100 ms, out of 14,594 scheduled. Each needed a fully observed preceding 267 ms, including hand and finger markers, plus a reference sample within 8 ms of the target. This is a retrospective selection, not a live test. We compared constant-velocity extrapolation with three ridge models of increasing state: ball and core body (M3), plus coarse hand (M3b), plus detailed hand and finger markers (M4). Models were trained leave-one-athlete-out, with regularisation chosen within training athletes, under a pre-registered tuning grid and a wider grid as sensitivity. After the whole-trial result existed, we grouped forecasts by timing relative to a retrospectively detected release, used only for evaluation. Post hoc intervals resample whole trials within each athlete.

**Results.** Across whole trials, constant velocity had the lowest error (150.5 mm); M4 was 8.0 mm worse, within trial-level variation (95% interval −18.7 to +23.8). More than 100 ms before release, M4 was worse on average for every athlete. In the final 100 ms, M4 erred by 124 mm against constant velocity's 197 mm (trial-level interval 66–79 mm better, 263 trials; Table 1). The advantage held across declared release boundaries and both grids (21–77 mm). It came from two athletes (−116, −118 mm); for the third, M4 was worse in every configuration (+12 to +71 mm). Of the 73 mm equal-athlete mean gain, 56 mm arises at the step from extrapolation to the fitted ball-and-body model, which changes estimator and inputs together. In the final 100 ms, detailed hands improved on coarse hands by 14.2 mm (12.4–16.1), except for the third athlete under the wider grid at two of three boundaries.

**Conclusion.** Just before release, fitted models were markedly better for two of three athletes; detailed hand markers added about 14 mm beyond coarse hands. Teams weighing hand-level capture should judge it by phase and athlete, not whole-trial averages. Three athletes cannot establish how this generalises. These are forecast errors against supplied motion capture, not tracking accuracy, and a live system would have to estimate the release phase itself.

**Table 1.** Mean per-athlete endpoint error (mm), pre-registered grid.

| Decision timing | Decisions | Constant velocity | M3 | M3b | M4 |
|---|---:|---:|---:|---:|---:|
| More than 100 ms before release | 4,382 | **66** | 79 | 80 | 83 |
| Within 100 ms before release | 263 | 197 | 141 | 138 | **124** |
| At or after release | 4,974 | **210** | 222 | 221 | 220 |
