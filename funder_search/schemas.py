import re
import json
from bs4 import BeautifulSoup
from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import MetaSchema, hide_relevance, relevance_score


class FunderSearchSchema(Schema):
    doi = fields.Str()
    snippets = fields.Method("get_snippet")
    html = fields.Str()
    relevance_score = fields.Method("get_relevance_score")

    @staticmethod
    def get_snippet(obj):
        if hasattr(obj.meta, 'highlight') and 'html' in obj.meta.highlight:
            cleaned_snippets = []
            seen_snippets = set()

            for fragment in obj.meta.highlight.html:
                # First, try to extract text from "_":"actual text" patterns (JSON values)
                json_texts = re.findall(r'["\']_["\']:\s*["\']([^"\']{20,}[^"\']*)["\']', fragment)

                if json_texts:
                    # If we found JSON text patterns, use those
                    for text in json_texts:
                        # Clean up the text
                        text = re.sub(r'\s+', ' ', text).strip()

                        # Deduplicate
                        text_normalized = re.sub(r'>>|<<', '', text).lower().strip()
                        if len(text) > 15 and text_normalized not in seen_snippets:
                            cleaned_snippets.append(text)
                            seen_snippets.add(text_normalized)
                else:
                    # Fallback: Use BeautifulSoup to extract text and strip all HTML tags
                    soup = BeautifulSoup(fragment, 'html.parser')
                    text = soup.get_text(separator=' ', strip=True)

                    # Remove JSON artifacts
                    text = re.sub(r'\{[^}]*\}|\[[^\]]*\]', ' ', text)
                    text = re.sub(r'#name:|id:|fn\d+|\$:|class=|>|<', ' ', text)

                    # Remove common metadata words
                    text = re.sub(r'\b(footnote|label|note-para|floats|footnotes|document|name|para)\b', ' ', text, flags=re.IGNORECASE)

                    # Clean up escaped characters and quotes
                    text = text.replace('\\"', '').replace("\\'", '').replace('\\', '').strip('"\'')

                    # Clean up whitespace
                    text = re.sub(r'\s+', ' ', text).strip()

                    # Deduplicate
                    text_normalized = re.sub(r'>>|<<', '', text).lower().strip()
                    if len(text) > 15 and text_normalized not in seen_snippets:
                        cleaned_snippets.append(text)
                        seen_snippets.add(text_normalized)

            return cleaned_snippets[:10] if cleaned_snippets else None  # Limit to 10 best snippets
        return None

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