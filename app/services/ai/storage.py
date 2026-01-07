"""
AI Chat Storage - Database operations for AI chat history.
Ported from src/core/StorageService.js (AI chat methods)
"""

from typing import Dict, List, Optional, Any
from app.core.database import db
from app.core.logger import Logger

logger = Logger("AiStorage")


class AiStorage:
    """Storage service for AI chats, messages, and settings."""

    async def ensure_tables(self):
        """Create AI-specific tables if they don't exist."""
        if not db.pool:
            return
        
        async with db.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_chats (
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
                CREATE TABLE IF NOT EXISTS ai_messages (
                    id SERIAL PRIMARY KEY,
                    chat_id INTEGER REFERENCES ai_chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_settings (
                    user_id BIGINT PRIMARY KEY,
                    provider TEXT DEFAULT 'groq',
                    model TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Token usage tracking per provider/model
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_token_usage (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(32) NOT NULL,
                    model VARCHAR(64) NOT NULL,
                    prompt_tokens BIGINT DEFAULT 0,
                    response_tokens BIGINT DEFAULT 0,
                    total_tokens BIGINT DEFAULT 0,
                    call_count INTEGER DEFAULT 1,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(provider, model)
                );
            """)
            
            logger.info("AI tables initialized")

    # ============= Chat Methods =============
    
    async def get_or_create_active_chat(self, user_id: int) -> Dict:
        """Get active chat or create new one."""
        if not db.pool:
            return {"id": None, "title": "New Chat", "user_id": user_id}
        
        # Find active chat
        row = await db.pool.fetchrow(
            "SELECT * FROM ai_chats WHERE user_id = $1 AND is_active = TRUE ORDER BY updated_at DESC LIMIT 1",
            user_id
        )
        
        if row:
            return dict(row)
        
        # Create new
        row = await db.pool.fetchrow(
            "INSERT INTO ai_chats (user_id) VALUES ($1) RETURNING *",
            user_id
        )
        return dict(row)

    async def create_new_chat(self, user_id: int) -> Dict:
        """Create a new chat and deactivate others."""
        if not db.pool:
            return {"id": None, "title": "New Chat"}
        
        # Deactivate all
        await db.pool.execute(
            "UPDATE ai_chats SET is_active = FALSE WHERE user_id = $1",
            user_id
        )
        
        # Create new
        row = await db.pool.fetchrow(
            "INSERT INTO ai_chats (user_id) VALUES ($1) RETURNING *",
            user_id
        )
        return dict(row)

    async def get_chat_by_id(self, chat_id: int) -> Optional[Dict]:
        if not db.pool:
            return None
        row = await db.pool.fetchrow("SELECT * FROM ai_chats WHERE id = $1", chat_id)
        return dict(row) if row else None

    async def get_user_chats(self, user_id: int, limit: int = 10) -> List[Dict]:
        if not db.pool:
            return []
        rows = await db.pool.fetch(
            "SELECT * FROM ai_chats WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2",
            user_id, limit
        )
        return [dict(r) for r in rows]

    async def set_active_chat(self, user_id: int, chat_id: int):
        if not db.pool:
            return
        await db.pool.execute("UPDATE ai_chats SET is_active = FALSE WHERE user_id = $1", user_id)
        await db.pool.execute("UPDATE ai_chats SET is_active = TRUE, updated_at = NOW() WHERE id = $1", chat_id)

    async def rename_chat(self, chat_id: int, title: str):
        if not db.pool:
            return
        await db.pool.execute("UPDATE ai_chats SET title = $1, updated_at = NOW() WHERE id = $2", title, chat_id)

    async def update_chat_summary(self, chat_id: int, summary: str):
        if not db.pool:
            return
        await db.pool.execute("UPDATE ai_chats SET summary = $1, updated_at = NOW() WHERE id = $2", summary, chat_id)

    async def delete_chat(self, chat_id: int):
        if not db.pool:
            return
        await db.pool.execute("DELETE FROM ai_chats WHERE id = $1", chat_id)

    # ============= Message Methods =============
    
    async def save_message(self, chat_id: int, role: str, content: str) -> Dict:
        if not db.pool:
            return {"id": None, "chat_id": chat_id, "role": role, "content": content}
        
        row = await db.pool.fetchrow(
            "INSERT INTO ai_messages (chat_id, role, content) VALUES ($1, $2, $3) RETURNING *",
            chat_id, role, content
        )
        
        # Update chat timestamp
        await db.pool.execute("UPDATE ai_chats SET updated_at = NOW() WHERE id = $1", chat_id)
        
        return dict(row)

    async def get_chat_messages(self, chat_id: int, limit: int = 10) -> List[Dict]:
        if not db.pool:
            return []
        rows = await db.pool.fetch(
            "SELECT * FROM ai_messages WHERE chat_id = $1 ORDER BY created_at DESC LIMIT $2",
            chat_id, limit
        )
        return [dict(r) for r in rows]

    async def get_message_count(self, chat_id: int) -> int:
        if not db.pool:
            return 0
        row = await db.pool.fetchrow("SELECT COUNT(*) FROM ai_messages WHERE chat_id = $1", chat_id)
        return int(row[0]) if row else 0

    async def clear_chat_messages(self, chat_id: int):
        if not db.pool:
            return
        await db.pool.execute("DELETE FROM ai_messages WHERE chat_id = $1", chat_id)

    # ============= Settings Methods =============
    
    async def get_settings(self, user_id: int) -> Dict:
        if not db.pool:
            return {"user_id": user_id, "provider": "groq", "model": "llama-3.3-70b-versatile"}
        
        row = await db.pool.fetchrow("SELECT * FROM ai_settings WHERE user_id = $1", user_id)
        
        if not row:
            # Create default
            await db.pool.execute(
                "INSERT INTO ai_settings (user_id, provider, model) VALUES ($1, 'groq', 'llama-3.3-70b-versatile')",
                user_id
            )
            return {"user_id": user_id, "provider": "groq", "model": "llama-3.3-70b-versatile"}
        
        return dict(row)

    async def update_settings(self, user_id: int, provider: str, model: str):
        if not db.pool:
            return
        await db.pool.execute(
            """INSERT INTO ai_settings (user_id, provider, model) VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE SET provider = $2, model = $3, updated_at = NOW()""",
            user_id, provider, model
        )


ai_storage = AiStorage()
