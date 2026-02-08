from sqlalchemy.ext.asyncio import AsyncSession


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db
