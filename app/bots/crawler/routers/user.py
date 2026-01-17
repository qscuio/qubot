"""
User Management Router

Handles user authorization: adding/removing allowed users, listing users.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.database import db

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Add User
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("useradd"))
async def cmd_useradd(message: types.Message, command: CommandObject):
    """Add a user to allowed list: /useradd <user_id> [username]"""
    if not await is_allowed(message.from_user.id):
        return

    if not command.args:
        await message.answer("❌ 用法: /useradd <user_id> [username]")
        return

    args = command.args.split()
    try:
        user_id = int(args[0])
    except ValueError:
        await message.answer("❌ user_id 必须是数字")
        return

    username = args[1] if len(args) > 1 else None

    if not db.pool:
        await message.answer("❌ 数据库未连接")
        return

    try:
        await db.pool.execute("""
            INSERT INTO allowed_users (user_id, username, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET username = $2
        """, user_id, username, message.from_user.id)

        name_str = f" (@{username})" if username else ""
        await message.answer(f"✅ 已添加用户: <code>{user_id}</code>{name_str}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ 添加失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Remove User
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("userdel"))
async def cmd_userdel(message: types.Message, command: CommandObject):
    """Remove a user from allowed list: /userdel <user_id>"""
    if not await is_allowed(message.from_user.id):
        return

    if not command.args:
        await message.answer("❌ 用法: /userdel <user_id>")
        return

    try:
        user_id = int(command.args.strip())
    except ValueError:
        await message.answer("❌ user_id 必须是数字")
        return

    if not db.pool:
        await message.answer("❌ 数据库未连接")
        return

    try:
        result = await db.pool.execute("""
            DELETE FROM allowed_users WHERE user_id = $1
        """, user_id)

        if result == "DELETE 1":
            await message.answer(f"✅ 已删除用户: <code>{user_id}</code>", parse_mode="HTML")
        else:
            await message.answer(f"⚠️ 用户不存在: <code>{user_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ 删除失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# List Users
# ─────────────────────────────────────────────────────────────────────────────

async def _get_userlist_ui() -> tuple[str, types.InlineKeyboardMarkup]:
    """Build user list UI."""
    db_users = []
    if db.pool:
        try:
            rows = await db.pool.fetch("""
                SELECT user_id, username, added_by, created_at
                FROM allowed_users ORDER BY created_at DESC
            """)
            db_users = list(rows)
        except Exception:
            pass

    text = "👤 <b>授权用户</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"

    if db_users:
        for row in db_users:
            username = f" (@{row['username']})" if row['username'] else ""
            source = " 🔒" if row['username'] == 'env' else ""
            text += f"  • <code>{row['user_id']}</code>{username}{source}\n"
    else:
        text += "📭 无授权用户 (允许所有人)"

    builder = InlineKeyboardBuilder()

    # Add delete buttons for users
    for row in db_users[:10]:
        label = f"❌ {row['username'] or row['user_id']}"
        builder.button(text=label, callback_data=f"user:del:{row['user_id']}")

    builder.button(text="🔄 刷新", callback_data="user:list")
    builder.button(text="◀️ 返回", callback_data="main")

    if db_users:
        builder.adjust(2, 2, 2, 2, 2, 2)
    else:
        builder.adjust(2)

    return text, builder.as_markup()


@router.message(Command("userlist"))
async def cmd_userlist(message: types.Message):
    """List all allowed users."""
    if not await is_allowed(message.from_user.id):
        return

    text, markup = await _get_userlist_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "user:list")
async def cb_userlist(callback: types.CallbackQuery):
    """Show user list via callback."""
    await safe_answer(callback)
    text, markup = await _get_userlist_ui()
    await safe_edit_text(callback.message, text, reply_markup=markup)


@router.callback_query(F.data.startswith("user:del:"))
async def cb_user_del(callback: types.CallbackQuery):
    """Delete user from allowed list."""
    user_id = int(callback.data.split(":")[2])

    if not db.pool:
        await safe_answer(callback, "❌ 数据库未连接")
        return

    try:
        await db.pool.execute("DELETE FROM allowed_users WHERE user_id = $1", user_id)
        await safe_answer(callback, "✅ 已删除")

        text, markup = await _get_userlist_ui()
        await safe_edit_text(callback.message, text, reply_markup=markup)
    except Exception as e:
        await safe_answer(callback, f"❌ 失败: {e}")
