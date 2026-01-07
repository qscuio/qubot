"""
Advanced AI Storage for agent sessions and tool execution logging.
"""

from typing import Dict, List, Optional, Any
from app.core.database import db
from app.core.logger import Logger

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
            
            # User agent preferences
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_agent_settings (
                    user_id BIGINT PRIMARY KEY,
                    default_agent TEXT DEFAULT 'chat',
                    auto_route BOOLEAN DEFAULT FALSE,
                    show_thinking BOOLEAN DEFAULT TRUE,
                    show_tool_calls BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
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
        if not db.pool:
            return {
                "user_id": user_id,
                "default_agent": "chat",
                "auto_route": False,
                "show_thinking": True,
                "show_tool_calls": True
            }
        
        row = await db.pool.fetchrow(
            "SELECT * FROM ai_agent_settings WHERE user_id = $1",
            user_id
        )
        
        if not row:
            await db.pool.execute(
                "INSERT INTO ai_agent_settings (user_id) VALUES ($1)",
                user_id
            )
            return {
                "user_id": user_id,
                "default_agent": "chat",
                "auto_route": False,
                "show_thinking": True,
                "show_tool_calls": True
            }
        
        return dict(row)
    
    async def update_agent_settings(
        self,
        user_id: int,
        default_agent: str = None,
        auto_route: bool = None,
        show_thinking: bool = None,
        show_tool_calls: bool = None
    ):
        """Update user's agent settings."""
        if not db.pool:
            return
        
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
        
        if updates:
            updates.append("updated_at = NOW()")
            await db.pool.execute(
                f"""INSERT INTO ai_agent_settings (user_id) VALUES ($1)
                    ON CONFLICT (user_id) DO UPDATE SET {', '.join(updates)}""",
                *values
            )


# Global storage instance
advanced_ai_storage = AdvancedAiStorage()
