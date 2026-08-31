from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends

from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.db.uow import UnitOfWork

SettingsDep = Annotated[AppSettings, Depends(get_settings)]


async def get_uow() -> AsyncGenerator[UnitOfWork, None]:
    """Provide one transactional Unit of Work per mutating/read API request."""

    async with UnitOfWork() as uow:
        try:
            yield uow
            await uow.commit()
        except BaseException:
            await uow.rollback()
            raise


UowDep = Annotated[UnitOfWork, Depends(get_uow)]
