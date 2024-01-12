from elasticsearch_dsl.query import Query


class TextExpansionQuery(Query):
    """
    Custom text_expansion query since current elasticsearch_dsl version does not support it.
    """

    name = "text_expansion"

    def __init__(self, sparse_vector_field, model_id, model_text, boost=None):
        if not sparse_vector_field or not isinstance(sparse_vector_field, str):
            raise ValueError("sparse_vector_field must be a non-empty string")
        if not model_id or not isinstance(model_id, str):
            raise ValueError("model_id must be a non-empty string")
        if not model_text or not isinstance(model_text, str):
            raise ValueError("model_text must be a non-empty string")
        if boost is not None and not isinstance(boost, (float, int)):
            raise ValueError("boost must be a float or integer")

        super().__init__()
        self.sparse_vector_field = sparse_vector_field
        self.model_id = model_id
        self.model_text = model_text
        self.boost = boost

    def to_dict(self, **kwargs):
        query_dict = {
            "text_expansion": {
                self.sparse_vector_field: {
                    "model_id": self.model_id,
                    "model_text": self.model_text,
                }
            }
        }
        if self.boost is not None:
            query_dict["text_expansion"][self.sparse_vector_field]["boost"] = self.boost
        return query_dict
