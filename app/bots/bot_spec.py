from dataclasses import dataclass
from typing import Optional, Sequence

from aiogram.types import BotCommand

from app.core.config import settings


@dataclass(frozen=True)
class BotSpec:
    name: str
    token_attr: str
    router_module: str
    commands: Sequence[BotCommand]

    @property
    def token(self) -> Optional[str]:
        return getattr(settings, self.token_attr, None)
