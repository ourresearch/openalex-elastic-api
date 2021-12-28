from core.exceptions import APIPaginationError, APIQueryParamsError


class Paginate:
    def __init__(self, page, per_page):
        self.max_per_page = 50
        self.max_result_size = 10000
        self.page = page
        self.per_page = per_page

    @property
    def start(self):
        if self.page == 1:
            return 0
        else:
            return (self.per_page * self.page) - self.per_page + 1

    @property
    def end(self):
        return self.per_page * self.page

    def validate(self):
        self.validate_per_page()
        self.validate_result_size()

    def validate_per_page(self):
        if self.per_page and self.per_page > self.max_per_page or self.per_page < 1:
            raise APIPaginationError(
                f"per-page parameter must be between 1 and {self.max_per_page}"
            )

    def validate_result_size(self):
        if self.page * self.per_page > self.max_result_size:
            raise APIPaginationError(
                f"Maximum results size of {self.max_result_size:,} records is exceeded. Cursor pagination is required for records beyond {self.max_result_size:,} and is coming soon."
            )
