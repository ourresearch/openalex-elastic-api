def clean_preference(preference):
    """Elastic throws error if preference starts with _."""
    if preference and preference.startswith("_"):
        preference = preference.replace("_", "underscore", 1)
    elif preference and preference.endswith("known") and preference != "known":
        preference = preference.replace("known", " ")
    return preference


def set_preference_for_filter_search(filter_params, s):
    preference = None
    for filter_param in filter_params:
        for key in filter_param:
            if key in [
                "abstract.search",
                "display_name.search",
                "title.search",
                "raw_affiliation_string.search",
            ]:
                preference = filter_param[key]
    if preference:
        s = s.params(preference=clean_preference(preference))
    return s