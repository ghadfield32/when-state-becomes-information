# Prior work and the novelty boundary

The study does not claim to invent pose-based basketball analysis, motion-capture
analysis, or forecasting from tracking state. Pose and rich shooting-measurement
work already has Sloan precedent, and this package treats that as established.

## Direct lineage

**SPL Open Data** — Maple Leaf Sports & Entertainment (MLSE), Sport Performance
Lab, Toronto.
Source: <https://github.com/Sport-Performance-Lab/SPL-Open-Data>, pinned at
`a3f9cffbde917b1e1747cedd6ec25dfab18c6051`. This package consumes that data; it
does not produce it. See `THIRD_PARTY_NOTICES.md` and `DATA.md`.

**Body-pose attributes in basketball.** *Body Shots: Analyzing Shooting Styles in
the NBA using Body Pose Attributes* (MIT Sloan Sports Analytics Conference) shows
that body-pose attributes have already been used for basketball shooting analysis.
It is cited here as the reason this paper does **not** claim novelty for using
body pose.

## What this work does not claim

- Not the first use of pose or body-state features for basketball.
- Not the first use of motion capture for shooting analysis.
- Not a new estimator. The models are ridge regression and constant-velocity
  extrapolation; the contribution is not a modelling technique.
- Not a tracking-system accuracy claim, and not a coaching or decision-value claim.

## The bounded contribution actually claimed

A **release-conditioned comparison of increasingly richer measured state against
constant velocity**, for a 100 ms ball forecast, with three specific things the
prior descriptive work does not provide here:

1. **A timing-conditioned contrast.** The value of richer state is measured
   *within* the shot relative to a retrospectively detected release, and it is
   negative before release and positive just before it.
2. **A decomposition of the gain.** The near-release improvement separates into
   extrapolation-to-fitted-body, coarse hand, and detailed hand steps, showing
   that most of the aggregate gain is not a finger-level effect.
3. **A preserved negative and heterogeneous result.** Constant velocity remains
   best across whole trials, richer state is worse early in the shot, and one of
   three athletes reverses the near-release result in every configuration.

That is an audited comparison of when additional measured state constitutes
forecast information, not a claim of a new method or of general superiority.

## Required before a broader claim

A paper asserting a general relationship between measured state and information
value would need athlete transfer beyond three athletes, leave-one-athlete-out
across a larger set, a learning curve, and measurement-quality validation. None
of those is claimed or performed here.
