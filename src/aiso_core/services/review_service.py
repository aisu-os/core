from sqlalchemy.ext.asyncio import AsyncSession


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
