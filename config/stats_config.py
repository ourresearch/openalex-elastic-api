stats_configs = [
    {
        "id": "count",
        "displayName": "Count",
        "description": "Number of documents",
        "newType": "number",
    },
    {
        "id": "average",
        "displayName": "Average",
        "description": "Average of a field",
        "newType": "number",
    },
    {
        "id": "median",
        "displayName": "Median",
        "description": "Median of a field",
        "newType": "number",
    },
    {
        "id": "sum",
        "displayName": "Sum",
        "description": "Sum of a field",
        "newType": "number",
    },
    {
        "id": "min",
        "displayName": "Min",
        "description": "Minimum of a field",
        "newType": "number",
    },
    {
        "id": "max",
        "displayName": "Max",
        "description": "Maximum of a field",
        "newType": "number",
    }
]

stats_configs_dict = {stat["id"]: stat for stat in stats_configs}
