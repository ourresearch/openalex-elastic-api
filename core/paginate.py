from core.exceptions import APIPaginationError
from core.export import is_group_by_export
from core.utils import set_number_param


class Paginate:
    def __init__(self, group_by, page, per_page, sample=None):
        self.group_by = group_by
        self.max_per_page = 1000
        self.max_result_size = 10000
        self.page = page
        self.per_page = per_page
        self.sample = sample

    @property
    def start(self):
        if self.page == 1:
            return 0
        else:
            return (self.per_page * self.page) - self.per_page

    @property
    def end(self):
        if self.sample and self.sample < self.per_page * self.page:
            return self.sample
        else:
            return self.per_page * self.page

    def validate(self):
        self.validate_page()
        self.validate_per_page()
        self.validate_result_size()

    def validate_page(self):
        if self.group_by and self.page != 1:
            raise APIPaginationError(
                "Unable to paginate beyond page 1. Group-by is limited to page 1 with up to 200 results at this time."
            )
        elif self.page < 1:
            raise APIPaginationError(f"Page parameter must be greater than 0.")

    def validate_per_page(self):
        if self.per_page and self.per_page > self.max_per_page or self.per_page < 1:
            raise APIPaginationError(
                f"per-page parameter must be between 1 and 1000"
            )

    def validate_result_size(self):
        if self.page * self.per_page > self.max_result_size:
            raise APIPaginationError(
                f"Maximum results size of {self.max_result_size:,} records is exceeded. Cursor pagination is required for records beyond {self.max_result_size:,}. See: https://docs.openalex.org/api#cursor-paging"
            )


def get_per_page(request):
    group_by = request.args.get("group_by") or request.args.get("group-by")
    if is_group_by_export(request):
        per_page = 200
    elif not group_by:
        per_page = set_number_param(request, "per-page", 25)
    else:
        per_page = set_number_param(request, "per-page", 200)
    return per_page


def get_pagination(params):
    paginate = Paginate(
        params["group_by"], params["page"], params["per_page"], params["sample"]
    )
    paginate.validate()
    return paginate
