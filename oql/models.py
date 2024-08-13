from extensions import db
from sqlalchemy import Column, BigInteger, String, Boolean, Integer, Float, ForeignKey


class Work(db.Model):
    __tablename__ = "work_mv"

    paper_id = Column(BigInteger, primary_key=True)
    original_title = Column(String(65535))
    doi_lower = Column(String(500))
    cited_by_count = Column(Integer)
    journal_id = Column(BigInteger)
    publication_date = Column(String(500))
    is_paratext = Column(Boolean)
    oa_status = Column(String(500))
    type = Column(String(500))
    type_crossref = Column(String(500))
    year = Column(Integer)
    created_date = Column(String(500))

    def __repr__(self):
        return f"<Work(paper_id={self.paper_id}, original_title={self.original_title})>"

    @property
    def id(self):
        return f"works/W{self.paper_id}"

    @property
    def display_name(self):
        return self.original_title

    @property
    def publication_year(self):
        return self.year

    @property
    def type_formatted(self):
        return {"id": f"types/{self.type}", "display_name": self.type}

    @property
    def primary_location(self):
        source = db.session.query(Source).filter_by(source_id=self.journal_id).first()
        if source:
            return {
                "source": {
                    "id": f"sources/S{source.source_id}",
                    "display_name": source.display_name,
                },
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
        # get the topic using the top scoring topic from the work_topic table
        result = (
            db.session.query(WorkTopic.topic_id, Topic.display_name)
            .join(Topic, WorkTopic.topic_id == Topic.topic_id)
            .filter(WorkTopic.paper_id == self.paper_id)
            .order_by(WorkTopic.score.desc())
            .first()
        )
        if result:
            return {"id": f"topics/T{result.topic_id}", "display_name": result.display_name}

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


class Affiliation(db.Model):
    __tablename__ = "affiliation"

    paper_id = Column(BigInteger, primary_key=True)
    author_id = Column(BigInteger, primary_key=True)
    affiliation_id = Column(BigInteger, primary_key=True)
    author_sequence_number = Column(Integer)
    original_author = Column(String(65535))
    original_orcid = Column(String(500))

    def __repr__(self):
        return f"<Affiliation(paper_id={self.paper_id}, author_id={self.author_id}, affiliation_id={self.affiliation_id})>"


class Author(db.Model):
    __tablename__ = "author"

    author_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535))

    def __repr__(self):
        return f"<Author(author_id={self.author_id}, display_name={self.display_name})>"


class Institution(db.Model):
    __tablename__ = "institution"

    affiliation_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    ror_id = Column(String(500), nullable=True)
    iso3166_code = Column(String(500), nullable=True)

    def __repr__(self):
        return f"<Institution(affiliation_id={self.affiliation_id}, display_name={self.display_name})>"


class Source(db.Model):
    __tablename__ = "source"

    source_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    type = Column(String(500), nullable=True)
    issn = Column(String(500), nullable=True)
    is_in_doaj = Column(Boolean, nullable=True)

    def __repr__(self):
        return f"<Source(source_id={self.source_id}, display_name={self.display_name})>"


class Topic(db.Model):
    __tablename__ = 'topic'

    topic_id = Column(Integer, primary_key=True)
    display_name = Column(String(65535), nullable=False)
    summary = Column(String(65535), nullable=True)
    keywords = Column(String(65535), nullable=True)
    subfield_id = Column(Integer, nullable=True)
    field_id = Column(Integer, nullable=True)
    domain_id = Column(Integer, nullable=True)
    wikipedia_url = Column(String(65535), nullable=True)

    def __repr__(self):
        return f"<Topic(topic_id={self.topic_id}, display_name={self.display_name})>"


class WorkTopic(db.Model):
    __tablename__ = 'work_topic'

    paper_id = Column(BigInteger, primary_key=True)
    topic_id = Column(Integer, primary_key=True)
    score = Column(Float, nullable=True)

    def __repr__(self):
        return f"<WorkTopic(paper_id={self.paper_id}, topic_id={self.topic_id}, score={self.score})>"
