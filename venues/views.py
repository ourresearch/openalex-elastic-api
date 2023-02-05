from flask import Blueprint, redirect, request, url_for

from core.utils import is_cached
from extensions import cache

blueprint = Blueprint("venues", __name__)


@blueprint.route("/venues")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def venues():
    return redirect(url_for("sources.sources", **request.args), code=301)


@blueprint.route("/venues/filters/<path:params>")
def venues_filters(params):
    return redirect(
        url_for("sources.sources_filters", params=params, **request.args), code=301
    )
