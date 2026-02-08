from fastapi import Query


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Sahifa raqami"),
        per_page: int = Query(20, ge=1, le=100, description="Har sahifadagi elementlar soni"),
    ):
        self.page = page
        self.per_page = per_page
        self.offset = (page - 1) * per_page
