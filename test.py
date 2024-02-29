@property
def siblings(self):
    siblings_query = (
        db.session.query(models.Topic)
        .filter(models.Topic.subfield_id == self.subfield_id)
        .all()
    )
    topics_list = [
        {"id": topic.openalex_id, "display_name": topic.display_name}
        for topic in siblings_query
        if topic.topic_id != self.topic_id
    ]
    topics_list_sorted = sorted(topics_list, key=lambda x: x["display_name"].lower())
    return topics_list_sorted
