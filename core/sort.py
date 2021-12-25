def sort_records(fields_dict, sort_params, s):
    sort_fields = []
    for key, value in sort_params.items():
        if key == "relevance_score":
            sort_fields.append("_score")
            continue

        field = fields_dict[key]
        if value == "asc":
            sort_fields.append(field.es_sort_field())
        elif value == "desc":
            sort_fields.append(f"-{field.es_sort_field()}")
    s = s.sort(*sort_fields)
    return s
