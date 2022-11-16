import csv
import datetime
import io

from flask import make_response
from openpyxl import Workbook
from openpyxl.writer.excel import save_virtual_workbook


def is_group_by_export(request):
    export_format = request.args.get("format")
    group_by = request.args.get("group_by") or request.args.get("group-by")
    return export_format and export_format.lower() in ["csv", "xlsx"] and group_by


def export_group_by(result, request):
    group_by_results = format_group_by_results(result)
    timestamp = get_timestamp()
    group_by_param = request.args.get("group_by") or request.args.get("group-by")
    export_format = request.args.get("format")
    filename = f"openalex-group-by-{group_by_param}-{timestamp}.{export_format.lower()}"

    if export_format.lower() == "csv":
        response = export_group_by_csv(filename, group_by_results)
    elif export_format.lower() == "xlsx":
        response = export_group_by_xlsx(filename, group_by_results)
    else:
        raise ValueError("Invalid format")
    return response


def export_group_by_csv(filename, group_by_results):
    # create csv
    string_io = io.StringIO()
    csv_writer = csv.DictWriter(
        string_io, fieldnames=["key", "key_display_name", "count"]
    )
    csv_writer.writeheader()
    csv_writer.writerows(group_by_results)

    # output
    output = make_response(string_io.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output


def export_group_by_xlsx(filename, group_by_results):
    wb = Workbook()
    ws = wb.active
    ws.append(["key", "key_display_name", "count"])
    for r in group_by_results:
        ws.append([r["key"], r["key_display_name"], r["count"]])

    # output
    output = make_response(save_virtual_workbook(wb))
    output.headers["Content-disposition"] = f"attachment; filename={filename}"
    output.headers[
        "Content-type"
    ] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return output


def format_group_by_results(result):
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
    return datetime.datetime.utcnow().strftime("%Y%m%d")
