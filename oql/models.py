from extensions import db
from sqlalchemy import Column, BigInteger, String, Boolean, Integer, Float, func, select
from sqlalchemy.ext.hybrid import hybrid_property


class Work(db.Model):
    __tablename__ = "work_mv"

    paper_id = Column(BigInteger, primary_key=True)
    original_title = Column(String(65535))
    doi = Column(String(500))
    doi_lower = Column(String(500))
    cited_by_count = Column(Integer)
    journal_id = Column(BigInteger)
    publication_date = Column(String(500))
    is_paratext = Column(Boolean)
    language = Column(String(300))
    oa_status = Column(String(500))
    is_oa = Column(Boolean)
    type = Column(String(500))
    type_crossref = Column(String(500))
    year = Column(Integer)
    fwci = Column(Float)
    topic_id = Column(Integer)
    topic_display_name = Column(String(65535))
    subfield_id = Column(Integer)
    subfield_display_name = Column(String(65535))
    field_id = Column(Integer)  
    field_display_name = Column(String(65535))
    domain_id = Column(Integer)  
    domain_display_name = Column(String(65535))
    primary_source_display_name = Column(String(65535))
    primary_source_type = Column(String(500))
    primary_source_issn = Column(String(500))
    primary_source_is_in_doaj = Column(Boolean)
    keyword_ids = Column(String(65535))
    keyword_display_names = Column(String(65535))
    institution_ids = Column(String(65535))
    institution_display_names = Column(String(65535))
    institution_types = Column(String(65535))
    ror_ids = Column(String(65535))
    orcid_ids = Column(String(65535))
    country_ids = Column(String(65535))
    country_display_names = Column(String(65535))
    continent_ids = Column(String(65535))
    continent_display_names = Column(String(65535))
    author_ids = Column(String(65535))
    author_display_names = Column(String(65535))
    funder_ids = Column(String(65535))
    funder_display_names = Column(String(65535))
    license = Column(String(500))
    is_retracted = Column(Boolean)
    created_date = Column(String(500))

    @property
    def id(self):
        return f"works/W{self.paper_id}"
    
    def __repr__(self):
        return f"<Work(paper_id={self.paper_id}, original_title={self.original_title})>"
    
class Abstract(db.Model):
    __tablename__ = "abstract"

    paper_id = Column(BigInteger, primary_key=True)
    abstract = Column(String(65535))    

    def __repr__(self):
        return f"<Abstract(paper_id={self.paper_id}, abstract={self.abstract})>"

        
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


class AffiliationAuthorDistinct(db.Model):
    __tablename__ = 'paper_author_distinct_mv'

    paper_id = db.Column(db.BigInteger, primary_key=True)
    author_ids = db.Column(db.String(65535))


class AffiliationCountryDistinct(db.Model):
    __tablename__ = "paper_country_distinct_mv"

    paper_id = Column(BigInteger, primary_key=True)
    country_id = Column(String(500))
    country_display_name = Column(String(65535))
    continent_id = Column(Integer)
    is_global_south = Column(Boolean)

    def __repr__(self):
        return f"<Affiliation(paper_id={self.paper_id}>"


class AffiliationContinentDistinct(db.Model):
    __tablename__ = "paper_continent_distinct_mv"

    paper_id = Column(BigInteger, primary_key=True)
    country_id = Column(String(500))
    continent_id = Column(Integer)
    is_global_south = Column(Boolean)

    def __repr__(self):
        return f"<Affiliation(paper_id={self.paper_id}>"


class AffiliationTypeDistinct(db.Model):
    __tablename__ = 'paper_type_distinct_mv'

    paper_id = db.Column(db.BigInteger, primary_key=True)
    type = db.Column(db.Text, primary_key=True)


class Author(db.Model):
    __tablename__ = "author_mv"

    author_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535))
    orcid = Column(String(500))
    has_orcid = Column(Boolean)
    affiliation_id = Column(String(500))
    affiliation_display_name = Column(String(65535))
    affiliation_type = Column(String(500))
    past_affiliation_ids = Column(String(65535))
    past_affiliation_display_names = Column(String(65535))
    past_affiliation_types = Column(String(65535))

    @hybrid_property
    def id(self):
        return f"authors/A{self.author_id}"

    @id.expression
    def id(cls):
        return func.concat('authors/A', cls.author_id)

    def __repr__(self):
        return f"<Author(author_id={self.author_id}, display_name={self.display_name})>"


class AuthorLastKnownInstitutions(db.Model):
    __tablename__ = "author_last_known_affiliations_mv"

    author_id = Column(BigInteger, primary_key=True)
    affiliation_id = Column(BigInteger, primary_key=True)
    paper_id = Column(BigInteger)
    display_name = Column(String(65535))
    year = Column(Integer)
    rank = Column(Integer)

    def __repr__(self):
        return f"<AuthorLastKnownInstitution(author_id={self.author_id}, affiliation_id={self.affiliation_id}, display_name={self.display_name})>"


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
        return f"<Country(country_code={self.country_id}, display_name={self.display_name})>"


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
    publisher_id = Column(BigInteger, nullable=True)

    @hybrid_property
    def id(self):
        return f"sources/S{self.source_id}"

    @id.expression
    def id(cls):
        return func.concat('sources/S', cls.source_id)

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

    def __repr__(self):
        return f"<Topic(topic_id={self.topic_id}, display_name={self.display_name})>"


class WorkFunder(db.Model):
    __tablename__ = "work_funder"

    paper_id = Column(BigInteger, primary_key=True)
    funder_id = Column(BigInteger, primary_key=True)

    def __repr__(self):
        return f"<WorkFunder(paper_id={self.paper_id}, funder_id={self.funder_id}>"


class WorkKeyword(db.Model):
    __tablename__ = "work_keyword"

    paper_id = Column(BigInteger, primary_key=True)
    keyword_id = Column(String(500), primary_key=True)
    score = Column(Float, nullable=True)

    def __repr__(self):
        return f"<WorkKeyword(paper_id={self.paper_id}, keyword_id={self.keyword_id})>"


class WorkSdg(db.Model):
    __tablename__ = "work_sdg"

    paper_id = Column(BigInteger, primary_key=True)
    sdg_id = Column(Integer, primary_key=True)
    score = Column(Float, nullable=True)

    def __repr__(self):
        return f"<WorkSdg(paper_id={self.paper_id}, sdg_id={self.sdg_id})>"


class WorkTopic(db.Model):
    __tablename__ = "work_topic"

    paper_id = Column(BigInteger, primary_key=True)
    topic_id = Column(Integer, primary_key=True)
    topic_rank = Column(Integer, nullable=False)
    score = Column(Float, nullable=True)

    def __repr__(self):
        return f"<WorkTopic(paper_id={self.paper_id}, topic_id={self.topic_id}, score={self.score})>"


class WorkType(db.Model):
    __tablename__ = "work_type"

    work_type_id = Column(String(500), primary_key=True)
    display_name = Column(String(65535), nullable=False)
    description = Column(String(65535), nullable=True)

    @property
    def id(self):
        return f"work-types/{self.work_type_id}"

    def __repr__(self):
        return f"<WorkType(type_id={self.work_type_id}, display_name={self.display_name})>"
        


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


def get_entity_class(entity):
    """
    Return the appropriate SQLAlchemy model class for the given entity name.
    """
    if entity == "countries":
        return Country
    elif entity == "institution-types":
        return InstitutionType
    elif entity == "source-types":
        return SourceType
    elif entity == "work-types":
        return WorkType
    elif entity == "summary":
        # "summary" also uses the Work model
        return Work
    else:
        # default: drop trailing "s" and capitalize, e.g. "authors" -> "Author"
        singular = entity[:-1].capitalize()
        return globals().get(singular, None) 


def is_model_property(column, entity_class):
    if not column:
        return False
    
    attr = getattr(entity_class, column, None)

    # check if it's a standard Python property
    if isinstance(attr, property):
        return True

    if isinstance(attr, hybrid_property):
        return False  # do not skip, we want to add hybrid properties

    if hasattr(attr, "expression"):
        return False  # do not skip, this is likely a hybrid property

    return False


def is_model_hybrid_property(column, entity_class):
    attr = getattr(entity_class, column, None)

    if isinstance(attr, hybrid_property):
        return True

    return False
