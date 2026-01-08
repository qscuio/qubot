from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from app.core.config import settings


class AllowedUsersMiddleware(BaseMiddleware):
    """
    Middleware that restricts bot access to ALLOWED_USERS only.
    If ALLOWED_USERS is not configured, ALL access is denied (invite-only).
    """
    async def __call__(self, handler, event, data):
        allowed = settings.allowed_users_list
        
        # Get user from event
        user = getattr(event, "from_user", None)
        
        # If allowed list is configured AND user is in it, allow access
        if allowed and user and user.id in allowed:
            return await handler(event, data)

        # Otherwise, deny access (either no allowed list configured, or user not in it)
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
            try:
                if event.message:
                    await event.message.answer("🔒 Invite-only bot. Ask the owner for access.")
            except Exception:
                pass
        elif isinstance(event, Message):
            try:
                await event.answer(
                    "🔒 Invite-only bot. Ask the owner for access."
                )
            except Exception:
                pass
        return None

