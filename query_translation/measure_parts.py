"""How each calculation measure behaves when its works come in parts (oxjob #2016; #1930's step 5): one table, read by
- analytics._measure_aggs: the Elasticsearch aggregation a measure runs as;
- walk_exec: a uniform sample of a set too big to hold (ESTIMABLE, scale_estimate) and an export's exact slices
  (SLICE_RULES, slice_measures, X-Set-Merge);
- id_split: the pieces of a big id filter, merged by the aggregation each measure runs as (AGG_MERGE).
Pieces and slices are both disjoint parts of the works, so a measure adds up the same way across either.
"""
from typing import NamedTuple, Optional, Tuple


class Parts(NamedTuple):
    agg: Optional[str]      # the ES aggregation it runs as (None: read from the bucket's own count or the group)
    sample: Optional[str]   # on a uniform sample of its set: "scale" it up, "keep" it as the sample has it; None: can't
    merge: Optional[str]    # across disjoint parts: "add", "min", "max", "mean" (a sum over a count of values),
                            # "percent" (a count over a count), "first" (the group's own field); None: can't
    helpers: Tuple[Tuple[str, bool], ...] = ()   # what a slice sends for it to add up: (measure, of its column?)


MEASURE_PARTS = {
    "count": Parts(None, "scale", "add"),
    "sum": Parts("sum", "scale", "add"),
    "values": Parts("value_count", None, "add"),   # works holding a value: a mean's denominator (only slices ask)
    "mean": Parts("avg", "keep", "mean", (("sum", True), ("values", True))),
    "min": Parts("min", None, "min"),
    "max": Parts("max", None, "max"),
    # a slice's numerator is percent x count / 100: exact while a slice holds under a million works (a partition holds
    # at most 65,536 keys, list_keys refuses past it: SLICE_PARTS x 65,536 = 524,288)
    "percent": Parts("filter", "keep", "percent", (("count", False),)),
    "median": Parts("percentiles", "keep", None),
    "percent_of_those": Parts(None, "keep", None),
    "value": Parts(None, "keep", "first"),
}

# What a big id filter's pieces merge by, per metric aggregation: the rule of the measure it runs as. Any other
# aggregation (percentiles: a median) runs whole. Filters, terms and composites merge by their own shape (id_split).
AGG_MERGE = {p.agg: p.merge for p in MEASURE_PARTS.values() if p.agg and p.merge in ("add", "min", "max", "mean")}
