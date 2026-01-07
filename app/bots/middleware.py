from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from app.core.config import settings


class AllowedUsersMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        allowed = settings.allowed_users_list
        if not allowed:
            return await handler(event, data)

        user = getattr(event, "from_user", None)
        if user and user.id in allowed:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
            try:
                if event.message:
                    await event.message.answer("Invite-only bot. Ask the owner for access.")
            except Exception:
                pass
        elif isinstance(event, Message):
            try:
                await event.answer(
                    "Invite-only bot. Ask the owner for access."
                )
            except Exception:
                pass
        return None
