"""
Portfolio Router

Handles real portfolio management: adding/removing positions, viewing P&L.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.portfolio import portfolio_service

from .common import is_allowed, safe_answer

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("port"))
async def cmd_port(message: types.Message, command: CommandObject):
    """Manage real portfolio.

    /port - Show portfolio
    /port add <code> <cost> <shares> - Add position
    /port del <code> - Remove position
    """
    if not await is_allowed(message.from_user.id):
        return

    args = command.args
    if not args:
        await _show_portfolio(message)
        return

    parts = args.split()
    action = parts[0].lower()

    if action == "add":
        # /port add <code> <cost> <shares>
        if len(parts) < 4:
            await message.answer("用法: /port add <代码> <成本价> <股数>")
            return

        code = parts[1]
        try:
            cost = float(parts[2])
            shares = int(parts[3])
        except ValueError:
            await message.answer("❌ 价格或股数格式错误")
            return

        success = await portfolio_service.add_position(message.from_user.id, code, cost, shares)
        if success:
            await message.answer(f"✅ 已添加 {code}: {shares}股 @ {cost}")
            await _show_portfolio(message)
        else:
            await message.answer("❌ 添加失败")

    elif action == "del":
        # /port del <code>
        if len(parts) < 2:
            await message.answer("用法: /port del <代码>")
            return

        code = parts[1]
        success = await portfolio_service.remove_position(message.from_user.id, code)
        if success:
            await message.answer(f"✅ 已删除 {code}")
            await _show_portfolio(message)
        else:
            await message.answer("❌ 删除失败")

    else:
        await message.answer(
            "💼 <b>持仓管理</b>\n\n"
            "• 查看: /port\n"
            "• 添加: /port add <代码> <成本> <股数>\n"
            "• 删除: /port del <代码>",
            parse_mode="HTML"
        )


async def _show_portfolio(message: types.Message):
    """Show portfolio with P&L."""
    portfolio = await portfolio_service.get_portfolio(message.from_user.id)

    if not portfolio:
        await message.answer(
            "💼 <b>实盘持仓</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 当前无持仓\n\n"
            "使用 /port add 添加",
            parse_mode="HTML"
        )
        return

    total_market = 0
    total_profit = 0
    total_cost = 0

    lines = ["💼 <b>实盘持仓</b>", "━━━━━━━━━━━━━━━━━━━━━"]

    for p in portfolio:
        name = p.get('name', p['code'])
        code = p['code']
        current = p.get('current_price', 0)
        cost = float(p['cost_price'])
        shares = p['shares']
        profit = p.get('profit', 0)
        profit_pct = p.get('profit_pct', 0)
        today_pct = p.get('today_change', 0)

        emoji = "🔴" if profit > 0 else ("🟢" if profit < 0 else "⚪")

        lines.append(
            f"{emoji} <b>{name}</b> ({code})\n"
            f"   现价: {current:.2f} ({today_pct:+.2f}%)\n"
            f"   持仓: {shares}股 @ {cost:.2f}\n"
            f"   盈亏: {profit:+,.0f} ({profit_pct:+.2f}%)"
        )

        total_market += p.get('market_value', 0)
        total_profit += profit
        total_cost += cost * shares

    total_return = (total_profit / total_cost * 100) if total_cost > 0 else 0

    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💰 总市值: ¥{total_market:,.0f}")
    lines.append(f"📈 总盈亏: ¥{total_profit:+,.0f} ({total_return:+.2f}%)")

    await message.answer("\n".join(lines), parse_mode="HTML")
