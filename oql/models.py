from extensions import db
from sqlalchemy import Column, BigInteger, String, Boolean, Integer, Float, func, select
from sqlalchemy.ext.hybrid import hybrid_property


class Work(db.Model):
    __tablename__ = "work_mv"

    paper_id = Column(BigInteger, primary_key=True)
    original_title = Column(String(65535))
    doi = Column(String(500))
    doi_lower = Column(String(500))
    cited_by_count = Column(Integer)  # joined from citation_papers_mv
    journal_id = Column(BigInteger)
    publication_date = Column(String(500))
    is_paratext = Column(Boolean)
    oa_status = Column(String(500))
    type = Column(String(500))
    type_crossref = Column(String(500))
    year = Column(Integer)
    fwci = Column(Float)
    topic_id = Column(Integer)  # joined from work_topic
    subfield_id = Column(Integer)  # joined rom work_topic
    field_id = Column(Integer)  # joined from work_topic
    domain_id = Column(Integer)  # joined from work_topic
    primary_source_display_name = Column(String(65535))
    primary_source_type = Column(String(500))
    primary_source_issn = Column(String(500))
    primary_source_is_in_doaj = Column(Boolean)
    created_date = Column(String(500))

    @property
    def id(self):
        return f"works/W{self.paper_id}"

    @hybrid_property
    def display_name(self):
        return self.original_title

    @display_name.expression
    def display_name(cls):
        return cls.original_title

    @property
    def type_formatted(self):
        return {"id": f"types/{self.type}", "display_name": self.type}

    @property
    def primary_location(self):
        source = db.session.query(Source).filter_by(source_id=self.journal_id).first()
        if source:
            return {
                "id": f"sources/S{source.source_id}",
                "display_name": source.display_name,
            }
        else:
            return None

    @property
    def authors(self):
        results = (
            db.session.query(Author.author_id, Author.display_name)
            .join(Affiliation, Affiliation.author_id == Author.author_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .order_by(Affiliation.author_sequence_number)
            .limit(10)
            .all()
        )
        return [
            {"id": f"authors/A{result.author_id}", "display_name": result.display_name}
            for result in results
        ]

    @property
    def topic(self):
        result = db.session.query(Topic).filter_by(topic_id=self.topic_id).first()
        if result:
            return {
                "id": f"topics/T{result.topic_id}",
                "display_name": result.display_name,
            }

    @property
    def subfield(self):
        result = db.session.query(Subfield).filter_by(subfield_id=self.subfield_id).first()
        if result:
            return {
                "id": f"subfields/{result.subfield_id}",
                "display_name": result.display_name,
            }

    @property
    def field(self):
        result = db.session.query(Field).filter_by(field_id=self.field_id).first()
        if result:
            return {
                "id": f"fields/{result.field_id}",
                "display_name": result.display_name,
            }

    @property
    def domain(self):
        result = db.session.query(Domain).filter_by(domain_id=self.domain_id).first()
        if result:
            return {
                "id": f"domains/{result.domain_id}",
                "display_name": result.display_name,
            }

    @property
    def keywords(self):
        results = (
            db.session.query(WorkKeyword.keyword_id, Keyword.display_name)
            .join(Keyword, WorkKeyword.keyword_id == Keyword.keyword_id)
            .filter(WorkKeyword.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        return [
            {"id": f"keywords/{keyword_id}", "display_name": display_name}
            for keyword_id, display_name in results
        ]

    @property
    def institutions(self):
        results = (
            db.session.query(Affiliation.affiliation_id, Institution.display_name)
            .join(Institution, Affiliation.affiliation_id == Institution.affiliation_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        # get unique institutions
        unique_institutions = {}
        for result in results:
            if result.affiliation_id not in unique_institutions:
                unique_institutions[result.affiliation_id] = result.display_name

        return [
            {
                "id": f"institutions/I{affiliation_id}",
                "display_name": display_name,
            }
            for affiliation_id, display_name in unique_institutions.items()
        ]

    @property
    def ror_ids(self):
        results = (
            db.session.query(Affiliation.ror)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        return list(set([result.ror for result in results]))

    @property
    def orcid_ids(self):
        results = (
            db.session.query(Author.orcid)
            .join(Affiliation, Affiliation.author_id == Author.author_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        return list(set([result.orcid for result in results if result.orcid]))

    @property
    def is_oa(self):
        return self.oa_status != "closed"

    @property
    def authorships_countries(self):
        results = (
            db.session.query(Affiliation.country_id, Affiliation.country_display_name)
            .join(Author, Affiliation.author_id == Author.author_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )

        # unique countries
        unique_countries = {}
        for result in results:
            if result.country_id and result.country_id not in unique_countries:
                unique_countries[result.country_id] = result.country_display_name

        return [
            {"id": f"countries/{country_id}", "display_name": display_name}
            for country_id, display_name in unique_countries.items()
        ]

    @property
    def authorships_continents(self):
        results = (
            db.session.query(Affiliation.continent_id, Affiliation.contintent_display_name)
            .join(Author, Affiliation.author_id == Author.author_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        return [
            {"id": f"continents/{result.continent_id, result.contintent_display_name}"}
            for result in results if result.continent_id
        ]

    @property
    def is_global_south(self):
        results = (
            db.session.query(Affiliation.is_global_south)
            .join(Author, Affiliation.author_id == Author.author_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        return any(result.is_global_south for result in results)

    @property
    def institution_types(self):
        results = (
            db.session.query(Institution.type)
            .join(Affiliation, Affiliation.affiliation_id == Institution.affiliation_id)
            .filter(Affiliation.paper_id == self.paper_id)
            .limit(10)
            .all()
        )
        return list(set([result.type for result in results]))

    def __repr__(self):
        return f"<Work(paper_id={self.paper_id}, original_title={self.original_title})>"


class Affiliation(db.Model):
    __tablename__ = "affiliation_mv"

    paper_id = Column(BigInteger, primary_key=True)
    author_id = Column(BigInteger, primary_key=True)
    affiliation_id = Column(BigInteger, primary_key=True)
    author_sequence_number = Column(Integer)
    original_author = Column(String(65535))
    original_orcid = Column(String(500))
    institution_display_name = Column(String(65535))
    ror = Column(String(500))
    type = Column(String(500))
    country_id = Column(String(500))
    country_display_name = Column(String(65535))
    continent_id = Column(Integer)
    is_global_south = Column(Boolean)

    def __repr__(self):
        return f"<Affiliation(paper_id={self.paper_id}, author_id={self.author_id}, affiliation_id={self.affiliation_id})>"


class AffiliationDistinct(db.Model):
    __tablename__ = "affiliation_distinct_mv"

    # This is a view that has unique paper_id, affiliation_id pairs to support filtering by institution
    # So when multiple authors from the same institution are on the same paper, we only get the paper_id returned once

    paper_id = Column(BigInteger, primary_key=True)
    author_id = Column(BigInteger, primary_key=True)
    affiliation_id = Column(BigInteger, primary_key=True)
    author_sequence_number = Column(Integer)
    original_author = Column(String(65535))
    original_orcid = Column(String(500))
    institution_display_name = Column(String(65535))
    ror = Column(String(500))
    type = Column(String(500))
    country_id = Column(String(500))
    country_display_name = Column(String(65535))
    continent_id = Column(Integer)
    is_global_south = Column(Boolean)

    def __repr__(self):
        return f"<AffiliationDistinct(paper_id={self.paper_id}, author_id={self.author_id}, affiliation_id={self.affiliation_id})>"


class Author(db.Model):
    __tablename__ = "author_mv"

    author_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535))
    orcid = Column(String(500))  # joined from author_orcid

    @hybrid_property
    def id(self):
        return f"authors/A{self.author_id}"

    @id.expression
    def id(cls):
        return func.concat('authors/A', cls.author_id)

    @property
    def affiliations(self):
        results = (
            db.session.query(Affiliation.affiliation_id, Institution.display_name)
            .join(Institution, Affiliation.affiliation_id == Institution.affiliation_id)
            .filter(Affiliation.author_id == self.author_id)
            .limit(10)
            .all()
        )
        return [
            {
                "id": f"institutions/I{result.affiliation_id}",
                "display_name": result.display_name,
            }
            for result in results
        ]

    @property
    def last_known_institutions(self):
        results = (
            db.session.query(Affiliation.affiliation_id, Institution.display_name)
            .join(Institution, Affiliation.affiliation_id == Institution.affiliation_id)
            .filter(Affiliation.author_id == self.author_id)
            .limit(2)
            .all()
        )
        seen = set()
        unique_results = []
        for result in results:
            if result.display_name not in seen:
                seen.add(result.display_name)
                unique_results.append(result)
                if len(unique_results) >= 10:
                    break

        return [
            {
                "id": f"institutions/I{result.affiliation_id}",
                "display_name": result.display_name,
            }
            for result in unique_results
        ]

    def __repr__(self):
        return f"<Author(author_id={self.author_id}, display_name={self.display_name})>"


class InstitutionCounts(db.Model):
    __tablename__ = "citation_institutions_mv"

    affiliation_id = Column(BigInteger, primary_key=True)
    paper_count = Column(Integer)
    oa_paper_count = Column(Integer)
    citation_count = Column(Integer)

    def __repr__(self):
        return f"<InstitutionCounts(affiliation_id={self.affiliation_id}, paper_count={self.paper_count})>"


class Country(db.Model):
    __tablename__ = "country"

    country_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)
    continent_id = Column(Integer, nullable=True)
    is_global_south = Column(Boolean, nullable=True)

    @hybrid_property
    def id(self):
        return f"countries/{self.country_id}"

    @id.expression
    def id(cls):
        return func.concat('countries/', cls.country_id)

    def __repr__(self):
        return f"<Country(country_code={self.country_code}, display_name={self.display_name})>"


class Continent(db.Model):
    __tablename__ = "continent"

    continent_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)
    wikidata_id = Column(String(500), nullable=True)

    @property
    def id(self):
        return f"continents/{self.wikidata_id}"

    def __repr__(self):
        return f"<Continent(continent_id={self.continent_id}, display_name={self.display_name})>"


class Domain(db.Model):
    __tablename__ = "domain"

    domain_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"domains/{self.domain_id}"

    def __repr__(self):
        return f"<Domain(domain_id={self.domain_id}, display_name={self.display_name})>"


class Field(db.Model):
    __tablename__ = "field"

    field_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"fields/{self.field_id}"

    def __repr__(self):
        return f"<Field(field_id={self.field_id}, display_name={self.display_name})>"


class Funder(db.Model):
    __tablename__ = "funder"

    funder_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)
    country_code = Column(String(500), nullable=True)
    doi = Column(String(500), nullable=True)
    ror_id = Column(String(500), nullable=True)
    crossref_id = Column(String(500), nullable=True)

    @property
    def id(self):
        return f"funders/F{self.funder_id}"

    @property
    def country_code_formatted(self):
        return (
            {"id": f"countries/{self.country_code}", "display_name": self.country_code}
            if self.country_code
            else None
        )

    def __repr__(self):
        return f"<Funder(funder_id={self.funder_id}, display_name={self.display_name})>"


class Institution(db.Model):
    __tablename__ = "institution_mv"

    affiliation_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    ror = Column(String(500), nullable=True)
    country_code = Column(String(500), nullable=True)
    type = Column(String(500), nullable=True)
    citations = Column(Integer)
    oa_paper_count = Column(Integer)

    @hybrid_property
    def id(self):
        return f"institutions/I{self.affiliation_id}"

    @id.expression
    def id(cls):
        return func.concat('institutions/I', cls.affiliation_id)

    @hybrid_property
    def type_formatted(self):
        return (
            {
                "id": f"institution-types/{self.type.lower()}",
                "display_name": self.type.lower(),
            }
            if self.type
            else None
        )

    @type_formatted.expression
    def type_formatted(cls):
        return (
            select([InstitutionType.display_name])
            .where(InstitutionType.institution_type_id == cls.type)
            .scalar_subquery()
        )

    @hybrid_property
    def mean_fwci(self):
        return (
            db.session.query(func.avg(Work.fwci))
            .join(Affiliation, Work.paper_id == Affiliation.paper_id)
            .filter(Affiliation.affiliation_id == self.affiliation_id)
            .scalar()
        )

    @mean_fwci.expression
    def mean_fwci(cls):
        # This is the expression form
        return (
            select([func.avg(Work.fwci)])
            .select_from(Work.join(Affiliation, Work.paper_id == Affiliation.paper_id))
            .where(Affiliation.affiliation_id == cls.affiliation_id)
            .scalar_subquery()
        )

    @property
    def country_code_formatted(self):
        return (
            {"id": f"countries/{self.country_code}", "display_name": self.country_code}
            if self.country_code
            else None
        )

    def __repr__(self):
        return f"<Institution(affiliation_id={self.affiliation_id}, display_name={self.display_name})>"


class InstitutionType(db.Model):
    __tablename__ = "institution_type"

    institution_type_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)

    @property
    def id(self):
        return f"institution-types/{self.institution_type_id}"

    def __repr__(self):
        return f"<InstitutionType(institution_type_id={self.institution_type_id}, display_name={self.display_name})>"


class Keyword(db.Model):
    __tablename__ = "keyword"

    keyword_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)

    @hybrid_property
    def id(self):
        return f"keywords/{self.keyword_id}"

    @id.expression
    def id(cls):
        return func.concat('keywords/', cls.keyword_id)

    def __repr__(self):
        return (
            f"<Keyword(keyword_id={self.keyword_id}, display_name={self.display_name})>"
        )


class Language(db.Model):
    __tablename__ = "language"

    language_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)

    @property
    def id(self):
        return f"languages/{self.language_id}"

    def __repr__(self):
        return f"<Language(language_id={self.language_id}, display_name={self.display_name})>"


class License(db.Model):
    __tablename__ = "license"

    license_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"licenses/{self.license_id}"

    def __repr__(self):
        return (
            f"<License(license_id={self.license_id}, display_name={self.display_name})>"
        )


class Publisher(db.Model):
    __tablename__ = "publisher"

    publisher_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    country_code = Column(String(500), nullable=True)

    @property
    def id(self):
        return f"publishers/P{self.publisher_id}"

    @property
    def country_code_formatted(self):
        return (
            {"id": f"countries/{self.country_code}", "display_name": self.country_code}
            if self.country_code
            else None
        )

    def __repr__(self):
        return f"<Publisher(publisher_id={self.publisher_id}, display_name={self.display_name})>"


class Sdg(db.Model):
    __tablename__ = "sdg"

    sdg_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"sdgs/{self.sdg_id}"

    def __repr__(self):
        return f"<SDG(sdg_id={self.sdg_id}, display_name={self.display_name})>"


class Source(db.Model):
    __tablename__ = "source"

    source_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    type = Column(String(500), nullable=True)
    issn = Column(String(500), nullable=True)
    is_in_doaj = Column(Boolean, nullable=True)
    journal_id = Column(BigInteger, nullable=True)

    @hybrid_property
    def id(self):
        return f"sources/S{self.source_id}"

    @id.expression
    def id(cls):
        return func.concat('sources/S', cls.source_id)

    @property
    def type_formatted(self):
        return (
            {
                "id": f"source-types/{self.type.lower()}",
                "display_name": self.type.lower(),
            }
            if self.type
            else None
        )

    def __repr__(self):
        return f"<Source(source_id={self.source_id}, display_name={self.display_name})>"


class SourceType(db.Model):
    __tablename__ = "source_type"

    source_type_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)

    @property
    def id(self):
        return f"source-types/{self.source_type_id}"

    def __repr__(self):
        return f"<SourceType(source_type_id={self.source_type_id}, display_name={self.display_name})>"


class Subfield(db.Model):
    __tablename__ = "subfield"

    subfield_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"subfields/{self.subfield_id}"

    def __repr__(self):
        return f"<Subfield(subfield_id={self.subfield_id}, display_name={self.display_name})>"


class Topic(db.Model):
    __tablename__ = "topic"

    topic_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    summary = Column(String(65535), nullable=True)
    keywords = Column(String(65535), nullable=True)
    subfield_id = Column(Integer, nullable=True)
    field_id = Column(Integer, nullable=True)
    domain_id = Column(Integer, nullable=True)
    wikipedia_url = Column(String(65535), nullable=True)

    @hybrid_property
    def id(self):
        return f"topics/T{self.topic_id}"

    @id.expression
    def id(cls):
        return func.concat('topics/T', cls.topic_id)

    @property
    def description(self):
        return self.summary

    @hybrid_property
    def domain(self):
        return self.domain_id

    @domain.expression
    def domain(cls):
        return cls.domain_id

    def __repr__(self):
        return f"<Topic(topic_id={self.topic_id}, display_name={self.display_name})>"


class WorkKeyword(db.Model):
    __tablename__ = "work_keyword"

    paper_id = Column(BigInteger, primary_key=True)
    keyword_id = Column(String(500), primary_key=True)
    score = Column(Float, nullable=True)

    def __repr__(self):
        return f"<WorkKeyword(paper_id={self.paper_id}, keyword_id={self.keyword_id})>"


class WorkTopic(db.Model):
    __tablename__ = "work_topic"

    paper_id = Column(BigInteger, primary_key=True)
    topic_id = Column(Integer, primary_key=True)
    topic_rank = Column(Integer, nullable=False)
    score = Column(Float, nullable=True)

    def __repr__(self):
        return f"<WorkTopic(paper_id={self.paper_id}, topic_id={self.topic_id}, score={self.score})>"


class Type(db.Model):
    __tablename__ = "work_type"

    work_type_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"work-types/{self.work_type_id}"

    def __repr__(self):
        return (
            f"<WorkType(type_id={self.work_type_id}, display_name={self.display_name})>"
        )


class AuthorOrcid(db.Model):
    __tablename__ = "author_orcid"

    author_id = Column(BigInteger, primary_key=True)
    orcid = Column(String(500), nullable=True)

    def __repr__(self):
        return f"<AuthorOrcid(author_id={self.author_id}, orcid={self.orcid})>"


class Ror(db.Model):
    __tablename__ = "ror"

    ror_id = Column(String(500), primary_key=True)
    name = Column(String(65535))
    city = Column(String(65535))
    state = Column(String(65535))
    country = Column(String(65535))
    country_code = Column(String(500))
    grid_id = Column(String(500))
    wikipedia_url = Column(String(65535))
    ror_type = Column(String(500))

    def __repr__(self):
        return "<Ror ( {} ) {}>".format(self.ror_id, self.name)
