from core.exceptions import APIPaginationError


class Paginate:
    def __init__(self, group_by, page, per_page):
        self.group_by = group_by
        self.max_per_page = 200
        self.max_result_size = 10000
        self.page = page
        self.per_page = per_page

    @property
    def start(self):
        if self.page == 1:
            return 0
        else:
            return (self.per_page * self.page) - self.per_page

    @property
    def end(self):
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
        if self.group_by and self.per_page != 200:
            raise APIPaginationError(
                "Unable to adjust per-page parameter with group-by. The per-page setting is set to display up to 200 results when using group-by and cannot be adjusted."
            )
        elif self.per_page and self.per_page > self.max_per_page or self.per_page < 1:
            raise APIPaginationError(
                f"per-page parameter must be between 1 and {self.max_per_page}"
            )

    def validate_result_size(self):
        if self.page * self.per_page > self.max_result_size:
            raise APIPaginationError(
                f"Maximum results size of {self.max_result_size:,} records is exceeded. Cursor pagination is required for records beyond {self.max_result_size:,}. See: https://docs.openalex.org/api#cursor-paging"
            )
