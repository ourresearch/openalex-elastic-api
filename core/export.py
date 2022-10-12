import csv
import datetime
import io

from flask import make_response
from werkzeug.wrappers import Response


def is_group_by_export(request):
    export_format = request.args.get("format")
    group_by = request.args.get("group_by") or request.args.get("group-by")
    if export_format and export_format.lower() == "csv" and group_by:
        return True
    else:
        return False


def generate_group_by_csv(result):
    # rename doc_count to count
    group_by_csv_results = get_group_by_results(result)

    # create csv
    string_io = io.StringIO()
    csv_writer = csv.DictWriter(
        string_io, fieldnames=["key", "key_display_name", "count"]
    )
    csv_writer.writeheader()
    csv_writer.writerows(group_by_csv_results)

    # output
    timestamp = get_timestamp()
    filename = f"openalex-group-by-{timestamp}.csv"
    output = Response(string_io.getvalue(), mimetype="text/csv")
    output.headers.set("Content-Disposition", "attachment", filename=f"{filename}")
    return output


def get_group_by_results(result):
    group_by_results = []
    for r in result["group_by"]:
        group_by_results.append(
            {
                "key": r["key"],
                "key_display_name": r["key_display_name"],
                "count": r["doc_count"],
            }
        )
    return group_by_results


def get_timestamp():
    return datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
