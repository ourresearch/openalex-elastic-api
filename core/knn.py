from elasticsearch_dsl.query import Query


class KNNQuery(Query):
    """
    Custom k-NN query for Elasticsearch, with optional similarity parameter.
    """

    name = "knn"

    def __init__(self, field, query_vector, num_candidates=None, similarity=None):
        if not field or not isinstance(field, str):
            raise ValueError("field must be a non-empty string")
        if not isinstance(query_vector, list) or not all(
            isinstance(item, (float, int)) for item in query_vector
        ):
            raise ValueError("query_vector must be a list of floats or integers")
        if num_candidates is not None and (
            not isinstance(num_candidates, int) or num_candidates <= 0
        ):
            raise ValueError("num_candidates must be a positive integer")
        if similarity is not None and not isinstance(similarity, float):
            raise ValueError("similarity must be a float")

        super().__init__()
        self.field = field
        self.query_vector = query_vector
        self.num_candidates = num_candidates
        self.similarity = similarity

    def to_dict(self, **kwargs):
        query_dict = {
            "knn": {
                "field": self.field,
                "query_vector": self.query_vector,
            }
        }
        if self.num_candidates is not None:
            query_dict["knn"]["num_candidates"] = self.num_candidates
        if self.similarity is not None:
            query_dict["knn"]["similarity"] = self.similarity
        return query_dict
