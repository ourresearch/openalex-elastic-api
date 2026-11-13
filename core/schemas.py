from marshmallow import INCLUDE, Schema, fields, post_dump

# Metric-aggregate group sort (oxjob #389) surfaces the metric value per group
# under a dynamic key `<metric>_<field>` (e.g. `mean_cited_by_count`). marshmallow
# drops undeclared keys on dump and the key name varies with the request, so we
# can't declare a fixed field; instead a @post_dump hook copies it back from the
# original group dict. These are the only metric prefixes we emit.
_GROUP_BY_METRIC_PREFIXES = ("mean_", "sum_", "min_", "max_")


class Rounded(fields.Float):
    """A float served to `places` decimals (Casey 11-12: 8.160333333333334 or 6.798047238270649e-08 reads as accuracy we
    don't have). Output only: the index keeps the full value, so filters and sorts read what they read before."""

    def __init__(self, places=2, **kwargs):
        super().__init__(**kwargs)
        self.places = places

    def _serialize(self, value, attr, obj, **kwargs):
        value = super()._serialize(value, attr, obj, **kwargs)
        return None if value is None else round(value, self.places)


class DoiUrl(fields.Str):
    """A DOI served as works serve theirs: https://doi.org/10.x/y, lower case (Casey 11-12). The index holds it bare
    (10.13039/100000002) or in an older URL form (http://dx.doi.org/10.3030/777483); a value with no DOI in it is
    served as stored."""

    def _serialize(self, value, attr, obj, **kwargs):
        value = super()._serialize(value, attr, obj, **kwargs)
        if not value:
            return value
        from ids.utils import normalize_doi   # ids.utils imports core: resolved at call time

        bare = normalize_doi(value, return_none_if_error=True)
        return f"https://doi.org/{bare}" if bare else value


class MetaSchema(Schema):
    count = fields.Int()
    q = fields.Str()
    db_response_time_ms = fields.Int()
    page = fields.Int()
    per_page = fields.Int()
    next_cursor = fields.Str()
    groups_count = fields.Int()
    apc_list_sum_usd = fields.Int()
    apc_paid_sum_usd = fields.Int()
    cited_by_count_sum = fields.Int()
    # rerank=true (oxjob #1521): whether this page's order came from Jev. Present
    # only when rerank was asked for.
    reranked = fields.Bool()
    # Why a page that asked for rerank came back in the normal order (oxjob #2003): search_busy (the proxy skipped it
    # while search is under heavy load), past_window (the page starts past the top 100), model_unavailable (the
    # reranking model didn't answer in time), disabled. Present only when reranked is false.
    rerank_reason = fields.Str()
    # Private, unstable query echo {oql, oqo, url} the GUI rehydrates from (oxjob
    # #373/#378). `fields.Raw` is a pass-through: marshmallow drops undeclared meta
    # keys on dump, so this field is what lets `core.shared_view`'s injected
    # `meta.x_query` survive serialization on every entity response. Omitted from
    # the payload when absent (no `dump_default`). The `x_` prefix signals it's
    # undocumented/mutable; it is deliberately NOT a `/properties` Field, so it
    # does not touch the properties drift gate.
    x_query = fields.Raw()
    # A list whose set in parentheses was too big to hold answers from a sample of it (oxjob #1930): its count is an
    # estimate, and `estimate` says how (sample_share, set_works, count_margin, rows, message). Present only then.
    approximate = fields.Bool()
    estimate = fields.Raw()

    class Meta:
        ordered = True


class GroupBySchema(Schema):
    key = fields.Str()
    key_display_name = fields.Str()
    count = fields.Int(attribute="doc_count")
    # Nested sub-groups for multi-dimensional (nested) group_by — oxjob #387.
    # Self-referential so every level renames doc_count -> count consistently.
    # marshmallow drops undeclared keys on dump, so without this the inner
    # `groups` list computed by core.group_by.results.get_nested_group_by_results
    # is silently stripped. Omitted from output for single-dim results (which
    # carry no `groups` key), so those responses stay byte-compatible.
    groups = fields.Nested(lambda: GroupBySchema(), many=True)

    class Meta:
        ordered = True

    @post_dump(pass_original=True)
    def _surface_metric_value(self, data, original, **kwargs):
        """Re-inject the dynamic metric-aggregate value (oxjob #389). The group
        dict from core.group_by.results carries a `<metric>_<field>` key (e.g.
        `mean_cited_by_count`) that marshmallow drops because it isn't a declared
        field; copy it through here. Appended after the declared fields so the
        output order stays key, key_display_name, count, [groups], <metric>."""
        if isinstance(original, dict):
            for k, v in original.items():
                if k.startswith(_GROUP_BY_METRIC_PREFIXES):
                    data[k] = v
        return data


class GroupBysSchema(Schema):
    group_by_key = fields.Str()
    groups = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True


class HistogramSchema(Schema):
    min = fields.Integer()
    key = fields.Integer()
    max = fields.Integer()
    count = fields.Int(attribute="doc_count")

    class Meta:
        ordered = True


class HistogramWrapperSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(HistogramSchema, many=True)

    class Meta:
        ordered = True


class APCByYearSchema(Schema):
    year = fields.Int()
    price = fields.Int()

    class Meta:
        ordered = True
        unknown = INCLUDE


class CountsByYearSchema(Schema):
    year = fields.Int()
    works_count = fields.Int()
    oa_works_count = fields.Int()
    cited_by_count = fields.Int()

    class Meta:
        ordered = True
        unknown = INCLUDE


class XConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()
    score = fields.Float()

    class Meta:
        ordered = True


class SummaryStatsSchema(Schema):
    two_year_mean_citedness = fields.Float(
        attribute="2yr_mean_citedness", data_key="2yr_mean_citedness"
    )
    h_index = fields.Int()
    i10_index = fields.Int()

    class Meta:
        ordered = True


class RoundedSummaryStatsSchema(SummaryStatsSchema):
    """summary_stats with the mean to 2 decimals: funders and sources (Casey 11-12). Authors and institutions keep
    SummaryStatsSchema until Casey or Jason says otherwise."""
    two_year_mean_citedness = Rounded(2, attribute="2yr_mean_citedness", data_key="2yr_mean_citedness")


class ValuesSchema(Schema):
    value = fields.Str()
    display_name = fields.Str()
    count = fields.Int()
    url = fields.Str()
    db_response_time_ms = fields.Int()

    class Meta:
        ordered = True


class FilterSchema(Schema):
    key = fields.Str()
    is_negated = fields.Boolean()
    type = fields.Str()
    values = fields.List(fields.Nested(ValuesSchema))

    class Meta:
        ordered = True


class FiltersWrapperSchema(Schema):
    filters = fields.Nested(FilterSchema, many=True)

    class Meta:
        ordered = True


class TopicHierarchySchema(Schema):
    id = fields.Str()
    display_name = fields.Str()

    class Meta:
        ordered = True


class TopicSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    count = fields.Int()
    value = fields.Float()
    score = fields.Float()
    subfield = fields.Nested(TopicHierarchySchema)
    field = fields.Nested(TopicHierarchySchema)
    domain = fields.Nested(TopicHierarchySchema)

    class Meta:
        ordered = True


class RolesSchema(Schema):
    role = fields.Str()
    id = fields.Str()
    works_count = fields.Int()

    class Meta:
        ordered = True


class PercentilesSchema(Schema):
    percentile = fields.Float()
    value = fields.Float()

    class Meta:
        ordered = True


class StatsMetaSchema(Schema):
    count = fields.Int()
    entity = fields.Str()
    filters = fields.List(fields.Dict())
    search = fields.Str()
    db_response_time_ms = fields.Int()

    class Meta:
        ordered = True


class StatsSchema(Schema):
    key = fields.Str()
    percentiles = fields.Dict(keys=fields.Integer(), values=fields.Integer())
    sum = fields.Integer()

    class Meta:
        ordered = True


class StatsWrapperSchema(Schema):
    meta = fields.Nested(StatsMetaSchema)
    stats = fields.Nested(StatsSchema, many=True)

    class Meta:
        ordered = True


def hide_relevance(data, context):
    if "relevance_score" in data.keys() and (
        not data["relevance_score"]
        and data["relevance_score"] != 0
        or "display_relevance" in context
        and context["display_relevance"] is False
    ):
        del data["relevance_score"]
    return data


def relevance_score(obj):
    if obj.meta.score and obj.meta != 0.0:
        return obj.meta.score
