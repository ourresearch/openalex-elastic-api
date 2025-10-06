import re
import json
from bs4 import BeautifulSoup
from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import MetaSchema, hide_relevance, relevance_score


class FunderSearchSchema(Schema):
    id = fields.Str()
    doi = fields.Str()
    snippets = fields.Method("get_snippet")
    html = fields.Str()
    relevance_score = fields.Method("get_relevance_score")

    @staticmethod
    def get_snippet(obj):
        if not hasattr(obj.meta, 'highlight'):
            return None

        # Check for either html or fulltext highlights
        highlight_field = None
        is_html = False
        if 'html' in obj.meta.highlight:
            highlight_field = obj.meta.highlight.html
            is_html = True
        elif 'fulltext' in obj.meta.highlight:
            highlight_field = obj.meta.highlight.fulltext
            is_html = False
        else:
            return None

        cleaned_snippets = []
        seen_snippets = set()

        for fragment in highlight_field:
            if is_html:
                # HTML processing - extract JSON text patterns
                json_texts = re.findall(r'["\']_["\']:\s*["\']([^"\']{20,}[^"\']*)["\']', fragment)

                if json_texts:
                    for text in json_texts:
                        text = re.sub(r'\s+', ' ', text).strip()
                        text_normalized = re.sub(r'>>|<<', '', text).lower().strip()
                        if len(text) > 15 and text_normalized not in seen_snippets:
                            cleaned_snippets.append(text)
                            seen_snippets.add(text_normalized)
                else:
                    # Fallback: Use BeautifulSoup
                    soup = BeautifulSoup(fragment, 'html.parser')
                    text = soup.get_text(separator=' ', strip=True)

                    # Remove JSON artifacts
                    text = re.sub(r'\{[^}]*\}|\[[^\]]*\]', ' ', text)
                    text = re.sub(r'#name:|id:|fn\d+|\$:|class=|>|<', ' ', text)
                    text = re.sub(r'\b(footnote|label|note-para|floats|footnotes|document|name|para)\b', ' ', text, flags=re.IGNORECASE)
                    text = text.replace('\\"', '').replace("\\'", '').replace('\\', '').strip('"\'')
                    text = re.sub(r'\s+', ' ', text).strip()

                    text_normalized = re.sub(r'>>|<<', '', text).lower().strip()
                    if len(text) > 15 and text_normalized not in seen_snippets:
                        cleaned_snippets.append(text)
                        seen_snippets.add(text_normalized)
            else:
                # Fulltext processing - simpler, already clean text
                text = fragment
                text = re.sub(r'\s+', ' ', text).strip()

                text_normalized = re.sub(r'>>|<<', '', text).lower().strip()
                if len(text) > 15 and text_normalized not in seen_snippets:
                    cleaned_snippets.append(text)
                    seen_snippets.add(text_normalized)

        return cleaned_snippets[:10] if cleaned_snippets else None

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        return hide_relevance(data, self.context)

    @staticmethod
    def get_relevance_score(obj):
        return relevance_score(obj)

    class Meta:
        ordered = True
        unknown = INCLUDE


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(FunderSearchSchema, many=True)

    class Meta:
        ordered = True