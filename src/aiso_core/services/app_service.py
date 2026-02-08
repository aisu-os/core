from sqlalchemy.ext.asyncio import AsyncSession


class AppService:
    def __init__(self, db: AsyncSession):
        self.db = db
