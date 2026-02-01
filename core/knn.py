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


class KNNQueryWithFilter:
    """
    kNN query with pre-filtering support for Elasticsearch 8.x.

    Uses the top-level knn parameter (not nested in query) which is required
    for pre-filtering to work correctly. Pre-filtering applies the filter
    BEFORE the vector search, reducing the search space.

    Example ES query structure:
    {
        "knn": {
            "field": "vector_embedding",
            "query_vector": [...],
            "k": 25,
            "num_candidates": 100,
            "filter": { "term": { "is_oa": true } }
        }
    }
    """

    def __init__(
        self,
        field: str,
        query_vector: list,
        k: int = 25,
        num_candidates: int = 100,
        filter_query: dict = None,
        similarity: float = None
    ):
        if not field or not isinstance(field, str):
            raise ValueError("field must be a non-empty string")
        if not isinstance(query_vector, list) or not all(
            isinstance(item, (float, int)) for item in query_vector
        ):
            raise ValueError("query_vector must be a list of floats or integers")
        if not isinstance(k, int) or k <= 0:
            raise ValueError("k must be a positive integer")
        if not isinstance(num_candidates, int) or num_candidates <= 0:
            raise ValueError("num_candidates must be a positive integer")
        if num_candidates < k:
            raise ValueError("num_candidates must be >= k")

        self.field = field
        self.query_vector = query_vector
        self.k = k
        self.num_candidates = num_candidates
        self.filter_query = filter_query
        self.similarity = similarity

    def to_dict(self) -> dict:
        """
        Build the knn query dict for Elasticsearch.

        Returns the knn clause to be used at top-level of search body,
        not nested within a "query" block.
        """
        knn = {
            "field": self.field,
            "query_vector": self.query_vector,
            "k": self.k,
            "num_candidates": self.num_candidates,
        }

        if self.filter_query is not None:
            knn["filter"] = self.filter_query

        if self.similarity is not None:
            knn["similarity"] = self.similarity

        return knn
