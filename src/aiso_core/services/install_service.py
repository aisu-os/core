from sqlalchemy.ext.asyncio import AsyncSession


class InstallService:
    def __init__(self, db: AsyncSession):
        self.db = db
