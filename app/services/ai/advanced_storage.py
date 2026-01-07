"""
Advanced AI Storage for agent sessions and tool execution logging.
"""

from typing import Dict, List, Optional, Any
from app.core.database import db
from app.core.logger import Logger
from app.core.config import settings

logger = Logger("AdvancedAiStorage")


class AdvancedAiStorage:
    """Storage service for advanced AI agent sessions and tool executions."""
    
    async def ensure_tables(self):
        """Create advanced AI tables if they don't exist."""
        if not db.pool:
            return
        
        async with db.pool.acquire() as conn:
            # Agent sessions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_agent_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    agent_name TEXT NOT NULL,
                    started_at TIMESTAMP DEFAULT NOW(),
                    ended_at TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    tool_call_count INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{}'
                );
            """)
            
            # Tool execution log table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_tool_executions (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES ai_agent_sessions(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments JSONB DEFAULT '{}',
                    result JSONB DEFAULT '{}',
                    success BOOLEAN DEFAULT TRUE,
                    executed_at TIMESTAMP DEFAULT NOW(),
                    duration_ms INTEGER
                );
            """)

            # Advanced AI chats
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_adv_chats (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    title TEXT DEFAULT 'New Chat',
                    summary TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_adv_messages (
                    id SERIAL PRIMARY KEY,
                    chat_id INTEGER REFERENCES ai_adv_chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # User agent preferences
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_agent_settings (
                    user_id BIGINT PRIMARY KEY,
                    default_agent TEXT DEFAULT 'chat',
                    auto_route BOOLEAN DEFAULT FALSE,
                    show_thinking BOOLEAN DEFAULT TRUE,
                    show_tool_calls BOOLEAN DEFAULT TRUE,
                    provider TEXT DEFAULT 'claude',
                    model TEXT,
                    chat_mode TEXT DEFAULT 'basic',
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Ensure new columns exist for existing installs
            await conn.execute("ALTER TABLE ai_agent_settings ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'claude';")
            await conn.execute("ALTER TABLE ai_agent_settings ADD COLUMN IF NOT EXISTS model TEXT;")
            await conn.execute("ALTER TABLE ai_agent_settings ADD COLUMN IF NOT EXISTS chat_mode TEXT DEFAULT 'basic';")
            
            logger.info("Advanced AI tables initialized")
    
    # ============= Session Methods =============
    
    async def create_session(self, user_id: int, agent_name: str) -> Optional[int]:
        """Create a new agent session."""
        if not db.pool:
            return None
        
        row = await db.pool.fetchrow(
            """INSERT INTO ai_agent_sessions (user_id, agent_name) 
               VALUES ($1, $2) RETURNING id""",
            user_id, agent_name
        )
        return row["id"] if row else None
    
    async def end_session(self, session_id: int):
        """End an agent session."""
        if not db.pool:
            return
        await db.pool.execute(
            "UPDATE ai_agent_sessions SET ended_at = NOW() WHERE id = $1",
            session_id
        )
    
    async def get_active_session(self, user_id: int) -> Optional[Dict]:
        """Get user's active session."""
        if not db.pool:
            return None
        
        row = await db.pool.fetchrow(
            """SELECT * FROM ai_agent_sessions 
               WHERE user_id = $1 AND ended_at IS NULL 
               ORDER BY started_at DESC LIMIT 1""",
            user_id
        )
        return dict(row) if row else None
    
    async def update_session_counts(self, session_id: int, messages: int = 0, tool_calls: int = 0):
        """Update session message and tool call counts."""
        if not db.pool:
            return
        await db.pool.execute(
            """UPDATE ai_agent_sessions 
               SET message_count = message_count + $1, 
                   tool_call_count = tool_call_count + $2 
               WHERE id = $3""",
            messages, tool_calls, session_id
        )
    
    # ============= Tool Execution Methods =============
    
    async def log_tool_execution(
        self,
        user_id: int,
        tool_name: str,
        arguments: Dict,
        result: Dict,
        success: bool,
        duration_ms: int = None,
        session_id: int = None
    ) -> Optional[int]:
        """Log a tool execution."""
        if not db.pool:
            return None
        
        import json
        row = await db.pool.fetchrow(
            """INSERT INTO ai_tool_executions 
               (session_id, user_id, tool_name, arguments, result, success, duration_ms)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            session_id, user_id, tool_name,
            json.dumps(arguments), json.dumps(result),
            success, duration_ms
        )
        return row["id"] if row else None
    
    async def get_recent_tool_executions(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get recent tool executions for a user."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch(
            """SELECT * FROM ai_tool_executions 
               WHERE user_id = $1 
               ORDER BY executed_at DESC LIMIT $2""",
            user_id, limit
        )
        return [dict(r) for r in rows]
    
    # ============= Settings Methods =============
    
    async def get_agent_settings(self, user_id: int) -> Dict:
        """Get user's agent settings."""
        default_provider = (settings.AI_ADVANCED_PROVIDER or "claude").lower()
        default_mode = "basic"
        if not db.pool:
            return {
                "user_id": user_id,
                "default_agent": "chat",
                "auto_route": False,
                "show_thinking": True,
                "show_tool_calls": True,
                "provider": default_provider,
                "model": None,
                "chat_mode": default_mode
            }
        
        row = await db.pool.fetchrow(
            "SELECT * FROM ai_agent_settings WHERE user_id = $1",
            user_id
        )
        
        if not row:
            await db.pool.execute(
                "INSERT INTO ai_agent_settings (user_id, provider, chat_mode) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO NOTHING",
                user_id, default_provider, default_mode
            )
            return {
                "user_id": user_id,
                "default_agent": "chat",
                "auto_route": False,
                "show_thinking": True,
                "show_tool_calls": True,
                "provider": default_provider,
                "model": None,
                "chat_mode": default_mode
            }

        data = dict(row)
        if not data.get("provider"):
            data["provider"] = default_provider
        if not data.get("chat_mode"):
            data["chat_mode"] = default_mode
        if "model" not in data:
            data["model"] = None

        return data
    
    async def update_agent_settings(
        self,
        user_id: int,
        default_agent: str = None,
        auto_route: bool = None,
        show_thinking: bool = None,
        show_tool_calls: bool = None,
        provider: str = None,
        model: str = None,
        chat_mode: str = None
    ):
        """Update user's agent settings."""
        if not db.pool:
            return
        
        # Ensure row exists with defaults
        await self.get_agent_settings(user_id)
        
        updates = []
        values = [user_id]
        param_idx = 2
        
        if default_agent is not None:
            updates.append(f"default_agent = ${param_idx}")
            values.append(default_agent)
            param_idx += 1
        
        if auto_route is not None:
            updates.append(f"auto_route = ${param_idx}")
            values.append(auto_route)
            param_idx += 1
        
        if show_thinking is not None:
            updates.append(f"show_thinking = ${param_idx}")
            values.append(show_thinking)
            param_idx += 1
        
        if show_tool_calls is not None:
            updates.append(f"show_tool_calls = ${param_idx}")
            values.append(show_tool_calls)
            param_idx += 1

        if provider is not None:
            updates.append(f"provider = ${param_idx}")
            values.append(provider)
            param_idx += 1

        if model is not None:
            updates.append(f"model = ${param_idx}")
            values.append(model)
            param_idx += 1

        if chat_mode is not None:
            updates.append(f"chat_mode = ${param_idx}")
            values.append(chat_mode)
            param_idx += 1
        
        if updates:
            updates.append("updated_at = NOW()")
            await db.pool.execute(
                f"""INSERT INTO ai_agent_settings (user_id) VALUES ($1)
                    ON CONFLICT (user_id) DO UPDATE SET {', '.join(updates)}""",
                *values
            )

    # ============= Advanced Chat Methods =============

    async def get_or_create_active_chat(self, user_id: int) -> Dict:
        """Get active advanced chat or create a new one."""
        if not db.pool:
            return {"id": None, "title": "New Chat", "user_id": user_id}
        
        row = await db.pool.fetchrow(
            "SELECT * FROM ai_adv_chats WHERE user_id = $1 AND is_active = TRUE ORDER BY updated_at DESC LIMIT 1",
            user_id
        )
        
        if row:
            return dict(row)
        
        row = await db.pool.fetchrow(
            "INSERT INTO ai_adv_chats (user_id) VALUES ($1) RETURNING *",
            user_id
        )
        return dict(row)

    async def create_new_chat(self, user_id: int) -> Dict:
        """Create a new advanced chat and deactivate others."""
        if not db.pool:
            return {"id": None, "title": "New Chat"}
        
        await db.pool.execute(
            "UPDATE ai_adv_chats SET is_active = FALSE WHERE user_id = $1",
            user_id
        )
        
        row = await db.pool.fetchrow(
            "INSERT INTO ai_adv_chats (user_id) VALUES ($1) RETURNING *",
            user_id
        )
        return dict(row)

    async def get_chat_by_id(self, chat_id: int) -> Optional[Dict]:
        if not db.pool:
            return None
        row = await db.pool.fetchrow("SELECT * FROM ai_adv_chats WHERE id = $1", chat_id)
        return dict(row) if row else None

    async def get_user_chats(self, user_id: int, limit: int = 10) -> List[Dict]:
        if not db.pool:
            return []
        rows = await db.pool.fetch(
            "SELECT * FROM ai_adv_chats WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2",
            user_id, limit
        )
        return [dict(r) for r in rows]

    async def set_active_chat(self, user_id: int, chat_id: int):
        if not db.pool:
            return
        await db.pool.execute("UPDATE ai_adv_chats SET is_active = FALSE WHERE user_id = $1", user_id)
        await db.pool.execute(
            "UPDATE ai_adv_chats SET is_active = TRUE, updated_at = NOW() WHERE id = $1",
            chat_id
        )

    async def rename_chat(self, chat_id: int, title: str):
        if not db.pool:
            return
        await db.pool.execute(
            "UPDATE ai_adv_chats SET title = $1, updated_at = NOW() WHERE id = $2",
            title, chat_id
        )

    async def update_chat_summary(self, chat_id: int, summary: str):
        if not db.pool:
            return
        await db.pool.execute(
            "UPDATE ai_adv_chats SET summary = $1, updated_at = NOW() WHERE id = $2",
            summary, chat_id
        )

    async def delete_chat(self, chat_id: int):
        if not db.pool:
            return
        await db.pool.execute("DELETE FROM ai_adv_chats WHERE id = $1", chat_id)

    async def save_message(self, chat_id: int, role: str, content: str) -> Dict:
        if not db.pool:
            return {"id": None, "chat_id": chat_id, "role": role, "content": content}
        
        row = await db.pool.fetchrow(
            "INSERT INTO ai_adv_messages (chat_id, role, content) VALUES ($1, $2, $3) RETURNING *",
            chat_id, role, content
        )
        
        await db.pool.execute("UPDATE ai_adv_chats SET updated_at = NOW() WHERE id = $1", chat_id)
        return dict(row)

    async def get_chat_messages(self, chat_id: int, limit: int = 10) -> List[Dict]:
        if not db.pool:
            return []
        rows = await db.pool.fetch(
            "SELECT * FROM ai_adv_messages WHERE chat_id = $1 ORDER BY created_at DESC LIMIT $2",
            chat_id, limit
        )
        return [dict(r) for r in rows]

    async def get_message_count(self, chat_id: int) -> int:
        if not db.pool:
            return 0
        row = await db.pool.fetchrow("SELECT COUNT(*) FROM ai_adv_messages WHERE chat_id = $1", chat_id)
        return int(row[0]) if row else 0

    async def clear_chat_messages(self, chat_id: int):
        if not db.pool:
            return
        await db.pool.execute("DELETE FROM ai_adv_messages WHERE chat_id = $1", chat_id)


# Global storage instance
advanced_ai_storage = AdvancedAiStorage()
