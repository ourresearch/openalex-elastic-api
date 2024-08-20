import os

from sqlalchemy import desc, func
from extensions import db
from oql import models
from sqlalchemy.ext.hybrid import hybrid_property


class RedshiftQueryHandler:
    def __init__(self, entity, sort_by_column, sort_by_order, filter_by, return_columns, valid_columns):
        self.entity = entity
        self.sort_by_column = sort_by_column
        self.sort_by_order = sort_by_order
        self.filter_by = filter_by
        self.return_columns = return_columns
        self.valid_columns = valid_columns
        self.model_return_columns = []

    def redshift_query(self):
        entity_class = self.get_entity_class()

        results = self.set_columns(entity_class)
        results = self.apply_sort(results, entity_class)
        results = self.apply_filter(results, entity_class)
        results = self.apply_stats(results, entity_class)
        return results.limit(100).all()

    def get_entity_class(self):
        if self.entity == "countries":
            entity_class = getattr(models, "Country")
        elif self.entity == "institution-types":
            entity_class = getattr(models, "InstitutionType")
        elif self.entity == "source-types":
            entity_class = getattr(models, "SourceType")
        elif self.entity == "work-types":
            entity_class = getattr(models, "WorkType")
        else:
            entity_class = getattr(models, self.entity[:-1].capitalize())
        return entity_class

    def set_columns(self, entity_class):
        columns_to_select = [entity_class]
        for column in self.return_columns:
            if column.startswith("count("):
                # set with stats function
                continue
            elif self.is_model_property(column, entity_class):
                print(f"column {column} is a model property")
                # continue if column is a model property
                continue
            elif column == "publication_year":
                columns_to_select.append(getattr(entity_class, "year", None))
            elif column == "mean(fwci)":
                columns_to_select.append(getattr(entity_class, "mean_fwci", None))
            else:
                columns_to_select.append(getattr(entity_class, column, None))
        # columns_to_select.append(getattr(entity_class, "id", None))  # always set id
        self.model_return_columns = columns_to_select
        results = db.session.query(*columns_to_select)
        return results

    def is_model_property(self, column, entity_class):
        attr = getattr(entity_class, column, None)

        # check if it's a standard Python property
        if isinstance(attr, property):
            return True

        if isinstance(attr, hybrid_property):
            return False  # Do not skip, we want to add hybrid properties

        if hasattr(attr, 'expression'):
            return False  # Do not skip, this is likely a hybrid property

        return False


    def apply_sort(self, query, entity_class):
        if self.sort_by_column:
            if self.sort_by_column == "count(works)":
                return query
            if self.sort_by_column == "publication_year":
                model_column = getattr(entity_class, "year")
            elif self.sort_by_column == "count(works)":
                print(f"sorting by count(works) for {self.entity}")
                model_column = getattr(entity_class, "count")
            else:
                model_column = getattr(entity_class, self.sort_by_column, None)

            if model_column:
                query = query.order_by(model_column) if self.sort_by_order == "asc" else query.order_by(desc(model_column))
            else:
                query = self.default_sort(query, entity_class)
        else:
            query = self.default_sort(query, entity_class)

        return query

    def default_sort(self, query, entity_class):
        default_sort_column = "cited_by_count" if self.entity == "works" else "display_name"
        return query.order_by(desc(getattr(entity_class, default_sort_column, None)))

    def apply_filter(self, query, entity_class):
        if not self.filter_by:
            return query

        filters = self.filter_by
        for key, value in filters.items():
            if key == "id":
                query = query.filter(getattr(entity_class, "paper_id") == value)
            elif key == "publication_year":
                query = query.filter(getattr(entity_class, "year") == value)
            else:
                column = getattr(entity_class, key, None)
                query = query.filter(column == value)
        return query

    def apply_stats(self, query, entity_class):
        if self.return_columns:
            for column in self.return_columns:
                if column == "count(works)" and self.entity == "authors":
                    stat, related_entity = parse_stats_column(column)

                    affiliation_class = getattr(models, "Affiliation")

                    # join
                    query = query.outerjoin(affiliation_class, affiliation_class.author_id == entity_class.author_id)

                    # group by
                    query = query.group_by(*self.model_return_columns)

                    # add stat column
                    query = query.add_columns(
                        func.count(func.distinct(affiliation_class.paper_id)).label(f"{stat}({related_entity})")
                    )

                    # sort here instead of in sort function
                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(func.count(func.distinct(affiliation_class.paper_id)).desc())
                        else:
                            query = query.order_by(func.count(func.distinct(affiliation_class.paper_id)).asc())

                elif column == "count(works)" and self.entity == "topics":
                    stat, related_entity = parse_stats_column(column)

                    work_topic_class = getattr(models, "WorkTopic")

                    query = query.outerjoin(work_topic_class, work_topic_class.topic_id == entity_class.topic_id)

                    query = query.group_by(*self.model_return_columns + [entity_class.topic_id])

                    query = query.filter(work_topic_class.topic_rank == 1)  # only take the first topic

                    query = query.add_columns(
                        func.count(func.distinct(work_topic_class.paper_id)).label(f"{stat}({related_entity})")
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(func.count(work_topic_class.paper_id).desc())
                        else:
                            query = query.order_by(func.count(work_topic_class.paper_id).asc())

                elif column == "count(works)" and self.entity == "institutions":
                    stat, related_entity = parse_stats_column(column)

                    affiliation_class = getattr(models, "Affiliation")

                    # join
                    query = query.outerjoin(affiliation_class, affiliation_class.affiliation_id == entity_class.affiliation_id)

                    # group by
                    query = query.group_by(
                        entity_class.id,
                        entity_class.affiliation_id,
                        entity_class.display_name
                    )

                    # add columns
                    query = query.add_columns(
                        func.count(func.distinct(affiliation_class.paper_id)).label(f"{stat}({related_entity})")
                    )

                    # sort here instead of in sort function
                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(func.count(func.distinct(affiliation_class.paper_id)).desc())
                        else:
                            query = query.order_by(func.count(func.distinct(affiliation_class.paper_id)).asc())

                elif column == "count(works)" and self.entity == "sources":
                    stat, related_entity = parse_stats_column(column)

                    work_class = getattr(models, "Work")

                    query = query.outerjoin(work_class, work_class.journal_id == entity_class.source_id)

                    query = query.group_by(*self.model_return_columns + [entity_class.source_id])

                    query = query.add_columns(
                        func.count(work_class.paper_id).label(f"{stat}({related_entity})")
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(func.count(work_class.paper_id).desc())
                        else:
                            query = query.order_by(func.count(work_class.paper_id).asc())

                elif column == "count(works)" and self.entity == "keywords":
                    stat, related_entity = parse_stats_column(column)

                    work_keyword_class = getattr(models, "WorkKeyword")

                    query = query.outerjoin(work_keyword_class, work_keyword_class.keyword_id == entity_class.keyword_id)

                    query = query.group_by(*self.model_return_columns + [entity_class.keyword_id])

                    query = query.add_columns(
                        func.count(work_keyword_class.paper_id).label(f"{stat}({related_entity})")
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(func.count(work_keyword_class.paper_id).desc())
                        else:
                            query = query.order_by(func.count(work_keyword_class.paper_id).asc())

                elif column == "count(works)" and self.entity == "countries":
                    stat, related_entity = parse_stats_column(column)

                    affiliation_class = getattr(models, "Affiliation")
                    institution_class = getattr(models, "Institution")

                    query = query.join(institution_class,
                                       affiliation_class.affiliation_id == institution_class.affiliation_id)

                    query = query.group_by(*self.model_return_columns + [institution_class.country_code])

                    query = query.add_columns(
                        institution_class.country_code,
                        func.count(func.distinct(affiliation_class.paper_id)).label(f"{stat}({related_entity})")
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(func.count(func.distinct(affiliation_class.paper_id)).desc())
                        else:
                            query = query.order_by(func.count(func.distinct(affiliation_class.paper_id)).asc())
        return query


def parse_stats_column(column):
    # use format like count(works) to get stat and entity
    stat = column.split("(")[0]
    entity = column.split("(")[1].split(")")[0]
    return stat, entity
