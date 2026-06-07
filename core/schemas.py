from marshmallow import INCLUDE, Schema, fields, post_dump

# Metric-aggregate group sort (oxjob #389) surfaces the metric value per group
# under a dynamic key `<metric>_<field>` (e.g. `mean_cited_by_count`). marshmallow
# drops undeclared keys on dump and the key name varies with the request, so we
# can't declare a fixed field; instead a @post_dump hook copies it back from the
# original group dict. These are the only metric prefixes we emit.
_GROUP_BY_METRIC_PREFIXES = ("mean_", "sum_", "min_", "max_")


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
    # Private, unstable query echo {oql, oqo, url} the GUI rehydrates from (oxjob
    # #373/#378). `fields.Raw` is a pass-through: marshmallow drops undeclared meta
    # keys on dump, so this field is what lets `core.shared_view`'s injected
    # `meta.x_query` survive serialization on every entity response. Omitted from
    # the payload when absent (no `dump_default`). The `x_` prefix signals it's
    # undocumented/mutable; it is deliberately NOT a `/properties` Field, so it
    # does not touch the properties drift gate.
    x_query = fields.Raw()

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
