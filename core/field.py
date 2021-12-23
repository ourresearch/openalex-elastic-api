class Field:
    """
    Defines a field that can be filtered, grouped, and sorted.
    """

    def __init__(
        self,
        param,
        custom_es_field=None,
        is_bool_query=False,
        is_date_query=False,
        is_range_query=False,
    ):
        self.param = param
        self.custom_es_field = custom_es_field
        self.is_bool_query = is_bool_query
        self.is_date_query = is_date_query
        self.is_range_query = is_range_query
        self.value = None

    def es_field(self) -> str:
        if self.custom_es_field:
            field = self.custom_es_field
        elif "." in self.param:
            field = self.param.replace(".", "__")
        else:
            field = self.param
        return field

    def es_sort_field(self):
        if self.custom_es_field:
            field = self.custom_es_field.replace("__", ".")
        elif self.param == "venue.publisher":
            field = f"{self.param}.keyword"
        else:
            field = self.param.replace("__", ".")
        return field

    def validate(self):
        if self.is_range_query and "<" in self.value or ">" in self.value:
            num = self.value[1:]
            try:
                n = int(num)
            except ValueError:
                print("not a number")
        elif self.is_range_query:
            pass
