"""Shared underwriting thresholds.

Keep analyst-tunable constants in one place so calculator, merger, and verdict
logic do not drift as the screening rules evolve.
"""

LINE_ITEMS_VS_RATIO_CUTOFF = 0.75
NOI_RECONCILIATION_GAP_PCT = 0.10
UNIT_MIX_GPR_MISMATCH_PCT = 0.05
ROLLOVER_CONCENTRATION_PCT = 0.40

INCOME_PERIOD_FULL_YEAR_MONTHS = 12
INCOME_PERIOD_SHORT_BAND = range(6, 12)
INCOME_PERIOD_VERY_SHORT_THRESHOLD = 3

DSCR_YEAR_ONE_FLOOR = 1.25
STRESS_DSCR_FLOOR = 1.15
