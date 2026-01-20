"""
Chat Memory Service - Main Orchestrator

Orchestrates the full extraction pipeline:
1. Chunk messages by topic
2. Extract structured info from each chunk
3. Merge into global memory
4. Validate with recall check
5. Render reports
"""

import time
import json
from datetime import datetime
from typing import List, Dict, Optional, Any

from app.core.logger import Logger
from app.core.database import db
from app.services.chat_memory.data_models import (
    GlobalMemory,
    ChunkExtraction,
    ProcessingResult,
    ClaimStatus,
    DecisionStatus,
    ActionStatus,
)
from app.services.chat_memory.chunker import TopicChunker, topic_chunker
from app.services.chat_memory.extractor import Extractor, extractor
from app.services.chat_memory.merger import MemoryMerger, memory_merger
from app.services.chat_memory.recall_checker import RecallChecker, recall_checker

logger = Logger("ChatMemoryService")


# ═══════════════════════════════════════════════════════════════════════════════
# Database Operations
# ═══════════════════════════════════════════════════════════════════════════════

async def ensure_tables():
    """Create chat memory tables if they don't exist."""
    if not db.pool:
        return
    
    async with db.pool.acquire() as conn:
        # Global channel memory (JSONB for flexibility)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_memory (
                id SERIAL PRIMARY KEY,
                channel_id TEXT UNIQUE NOT NULL,
                channel_name TEXT,
                memory JSONB NOT NULL,
                version INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Index for quick lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_memory_channel 
            ON chat_memory(channel_id);
        """)
        
        # Individual extractions for traceability
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_extractions (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                extraction JSONB NOT NULL,
                message_count INT,
                time_start TIMESTAMP,
                time_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Index for extraction queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_extractions_channel 
            ON chat_extractions(channel_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_extractions_time 
            ON chat_extractions(created_at DESC);
        """)
        
        # Quality metrics tracking
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS extraction_metrics (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL,
                date DATE NOT NULL,
                hard_fact_recall DECIMAL,
                traceability_pct DECIMAL,
                stability_score DECIMAL,
                chunks_processed INT,
                messages_processed INT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(channel_id, date)
            );
        """)
        
        logger.info("📦 Chat memory tables initialized")


async def load_memory(channel_id: str) -> Optional[GlobalMemory]:
    """Load global memory for a channel from database."""
    if not db.pool:
        return None
    
    try:
        row = await db.pool.fetchrow(
            "SELECT memory, channel_name FROM chat_memory WHERE channel_id = $1",
            channel_id
        )
        if row:
            memory_data = row['memory']
            if isinstance(memory_data, str):
                memory_data = json.loads(memory_data)
            return GlobalMemory.from_dict(memory_data)
    except Exception as e:
        logger.error(f"Failed to load memory: {e}")
    
    return None


async def save_memory(memory: GlobalMemory):
    """Save global memory to database."""
    if not db.pool:
        return
    
    try:
        memory_json = json.dumps(memory.to_dict(), ensure_ascii=False)
        await db.pool.execute("""
            INSERT INTO chat_memory (channel_id, channel_name, memory, version, updated_at)
            VALUES ($1, $2, $3::jsonb, $4, NOW())
            ON CONFLICT (channel_id) 
            DO UPDATE SET 
                memory = $3::jsonb,
                version = $4,
                updated_at = NOW()
        """, memory.channel_id, memory.channel_name, memory_json, memory.version)
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")


async def save_extraction(extraction: ChunkExtraction):
    """Save individual extraction for traceability."""
    if not db.pool:
        return
    
    try:
        extraction_json = json.dumps(extraction.to_dict(), ensure_ascii=False)
        
        # Parse timestamps
        time_start = None
        time_end = None
        if extraction.time_start:
            try:
                time_start = datetime.fromisoformat(extraction.time_start.replace('Z', '+00:00'))
            except:
                pass
        if extraction.time_end:
            try:
                time_end = datetime.fromisoformat(extraction.time_end.replace('Z', '+00:00'))
            except:
                pass
        
        await db.pool.execute("""
            INSERT INTO chat_extractions 
            (channel_id, chunk_id, extraction, message_count, time_start, time_end)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6)
        """, extraction.channel_id, extraction.chunk_id, extraction_json,
             extraction.message_count, time_start, time_end)
    except Exception as e:
        logger.error(f"Failed to save extraction: {e}")


async def save_metrics(
    channel_id: str,
    hard_fact_recall: float,
    traceability: float,
    chunks_processed: int,
    messages_processed: int,
):
    """Save quality metrics."""
    if not db.pool:
        return
    
    try:
        today = datetime.now().date()
        await db.pool.execute("""
            INSERT INTO extraction_metrics 
            (channel_id, date, hard_fact_recall, traceability_pct, chunks_processed, messages_processed)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (channel_id, date) 
            DO UPDATE SET 
                hard_fact_recall = $3,
                traceability_pct = $4,
                chunks_processed = extraction_metrics.chunks_processed + $5,
                messages_processed = extraction_metrics.messages_processed + $6
        """, channel_id, today, hard_fact_recall, traceability, chunks_processed, messages_processed)
    except Exception as e:
        logger.error(f"Failed to save metrics: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Report Rendering
# ═══════════════════════════════════════════════════════════════════════════════

def render_report(memory: GlobalMemory, result: ProcessingResult) -> str:
    """
    Render global memory as a readable report.
    
    Format:
    - 核心要点 (key claims)
    - 决策与行动 (decisions + actions)
    - 约束与风险 (constraints)
    - 观点与讨论 (claims with disputes)
    - 待解决问题 (open questions)
    """
    now = datetime.now()
    report_type = "早报" if now.hour < 12 else "晚报"
    date_str = now.strftime("%Y年%m月%d日")
    
    lines = [
        f"# 📊 {memory.channel_name} {report_type}",
        f"> {date_str} | 消息 {memory.total_messages_processed} 条 | 可追溯性 {memory.traceability_score:.0%}",
        "",
    ]
    
    # ─────────────────────────────────────────────────────────────────────────
    # 核心要点 (Top claims by importance)
    # ─────────────────────────────────────────────────────────────────────────
    active_claims = [c for c in memory.claims.values() if c.status == ClaimStatus.ACTIVE]
    if active_claims:
        lines.append("## 🎯 核心要点")
        for claim in active_claims[:5]:  # Top 5
            evidence_note = ""
            if claim.evidence:
                ev = claim.evidence[0]
                evidence_note = f" *— {ev.speaker}*"
            lines.append(f"- {claim.claim}{evidence_note}")
        lines.append("")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 决策与行动
    # ─────────────────────────────────────────────────────────────────────────
    confirmed_decisions = [
        d for d in memory.decisions.values() 
        if d.status == DecisionStatus.CONFIRMED
    ]
    open_actions = [
        a for a in memory.action_items.values() 
        if a.status in (ActionStatus.OPEN, ActionStatus.DOING)
    ]
    
    if confirmed_decisions or open_actions:
        lines.append("## 📋 决策与行动")
        
        if confirmed_decisions:
            lines.append("**决策:**")
            for dec in confirmed_decisions[:5]:
                evidence_note = ""
                if dec.evidence:
                    ev = dec.evidence[0]
                    evidence_note = f" *— {ev.speaker}*"
                lines.append(f"- ✅ {dec.decision}{evidence_note}")
        
        if open_actions:
            lines.append("\n**待办:**")
            for action in open_actions[:5]:
                status_emoji = "🔄" if action.status == ActionStatus.DOING else "⏳"
                due_note = f" (截止: {action.due})" if action.due else ""
                lines.append(f"- {status_emoji} {action.task} @{action.owner}{due_note}")
        
        lines.append("")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 约束与风险
    # ─────────────────────────────────────────────────────────────────────────
    active_constraints = [c for c in memory.constraints.values() if c.is_active]
    if active_constraints:
        lines.append("## ⚠️ 约束与风险")
        for con in active_constraints[:5]:
            hard_marker = "🔒" if con.is_hard else "📌"
            lines.append(f"- {hard_marker} [{con.type.value}] {con.constraint}")
        lines.append("")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 分歧与争议
    # ─────────────────────────────────────────────────────────────────────────
    disputed_claims = [c for c in memory.claims.values() if c.status == ClaimStatus.DISPUTED]
    if disputed_claims:
        lines.append("## 💬 分歧与争议")
        for claim in disputed_claims[:3]:
            lines.append(f"- **{claim.speaker}**: {claim.claim}")
            if claim.counterpoints:
                lines.append(f"  - 反对观点: {claim.counterpoints[0][:100]}")
        lines.append("")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 待解决问题
    # ─────────────────────────────────────────────────────────────────────────
    open_questions = [q for q in memory.open_questions.values() if not q.is_resolved]
    if open_questions:
        lines.append("## ❓ 待解决")
        for q in open_questions[:5]:
            lines.append(f"- {q.question} *— {q.raised_by}*")
        lines.append("")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Footer
    # ─────────────────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append(
        f"*处理统计: {result.chunks_processed} 块 | "
        f"+{result.new_claims} 观点 | "
        f"+{result.new_decisions} 决策 | "
        f"+{result.new_actions} 待办 | "
        f"{result.merged_claims} 合并 | "
        f"{result.conflicts_detected} 争议*"
    )
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Service
# ═══════════════════════════════════════════════════════════════════════════════

class ChatMemoryService:
    """
    Main orchestrator for structured extraction pipeline.
    
    Pipeline:
    1. Chunk messages by topic
    2. Extract structured info from each chunk (two-pass)
    3. Merge into global memory (diff-based)
    4. Validate with recall check
    5. Persist and render report
    """
    
    def __init__(self):
        self.chunker = topic_chunker
        self.extractor = extractor
        self.merger = memory_merger
        self.recall_checker = recall_checker
        self._initialized = False
    
    async def initialize(self):
        """Initialize database tables."""
        if not self._initialized:
            await ensure_tables()
            self._initialized = True
    
    async def process_messages(
        self,
        channel_id: str,
        channel_name: str,
        messages: List[Dict],
    ) -> ProcessingResult:
        """
        Process messages through the full extraction pipeline.
        
        Args:
            channel_id: Channel identifier
            channel_name: Channel display name
            messages: Raw messages from database
            
        Returns:
            ProcessingResult with updated memory and statistics
        """
        start_time = time.time()
        
        await self.initialize()
        
        if not messages:
            logger.info(f"No messages to process for {channel_name}")
            memory = await load_memory(channel_id) or GlobalMemory.create_empty(channel_id, channel_name)
            return ProcessingResult(
                memory=memory,
                chunks_processed=0,
                messages_processed=0,
                new_claims=0,
                new_decisions=0,
                new_actions=0,
                new_constraints=0,
            )
        
        logger.info(f"📚 Processing {len(messages)} messages for {channel_name}")
        
        # Step 1: Load or create global memory
        memory = await load_memory(channel_id)
        if not memory:
            memory = GlobalMemory.create_empty(channel_id, channel_name)
            logger.info(f"📝 Created new memory for {channel_name}")
        
        # Step 2: Chunk messages
        chunks = self.chunker.chunk_messages(messages, channel_id)
        logger.info(f"📦 Created {len(chunks)} chunks")
        
        # Step 3: Process each chunk
        total_stats = {
            'new_claims': 0,
            'new_decisions': 0,
            'new_actions': 0,
            'new_constraints': 0,
            'merged_claims': 0,
            'superseded_claims': 0,
            'disputed_claims': 0,
        }
        
        total_recall = 0.0
        
        for chunk in chunks:
            # Extract
            extraction = await self.extractor.extract(chunk, channel_id, channel_name)
            
            # Save extraction for traceability
            await save_extraction(extraction)
            
            # Merge into memory
            memory, stats = self.merger.merge(extraction, memory)
            
            # Accumulate stats
            for key in total_stats:
                if key in stats:
                    total_stats[key] += stats[key]
            
            # Recall check (sample-based for performance)
            if len(chunks) <= 10 or chunks.index(chunk) % 5 == 0:
                chunk_messages = [
                    {'message_text': m.text, 'sender_name': m.sender, 'timestamp': m.timestamp}
                    for m in chunk.messages
                ]
                recall_report = self.recall_checker.check(chunk_messages, extraction)
                total_recall += recall_report.recall_score
        
        # Step 4: Save updated memory
        await save_memory(memory)
        
        # Step 5: Calculate final metrics
        avg_recall = total_recall / len(chunks) if chunks else 1.0
        traceability = memory.traceability_score
        
        # Save metrics
        await save_metrics(
            channel_id=channel_id,
            hard_fact_recall=avg_recall,
            traceability=traceability,
            chunks_processed=len(chunks),
            messages_processed=len(messages),
        )
        
        # Build result
        processing_time = (time.time() - start_time) * 1000
        
        result = ProcessingResult(
            memory=memory,
            chunks_processed=len(chunks),
            messages_processed=len(messages),
            new_claims=total_stats['new_claims'],
            new_decisions=total_stats['new_decisions'],
            new_actions=total_stats['new_actions'],
            new_constraints=total_stats['new_constraints'],
            merged_claims=total_stats['merged_claims'],
            superseded_claims=total_stats['superseded_claims'],
            conflicts_detected=total_stats['disputed_claims'],
            hard_fact_recall=avg_recall,
            traceability=traceability,
            processing_time_ms=processing_time,
        )
        
        logger.info(
            f"✅ Processed {channel_name}: "
            f"{len(chunks)} chunks, "
            f"{result.new_claims} claims, "
            f"{result.new_decisions} decisions, "
            f"recall={avg_recall:.1%}, "
            f"time={processing_time:.0f}ms"
        )
        
        return result
    
    async def get_memory(self, channel_id: str) -> Optional[GlobalMemory]:
        """Get global memory for a channel."""
        await self.initialize()
        return await load_memory(channel_id)
    
    async def clear_memory(self, channel_id: str):
        """Clear memory for a channel (for testing/reset)."""
        if not db.pool:
            return
        
        try:
            await db.pool.execute("DELETE FROM chat_memory WHERE channel_id = $1", channel_id)
            await db.pool.execute("DELETE FROM chat_extractions WHERE channel_id = $1", channel_id)
            logger.info(f"🗑️ Cleared memory for {channel_id}")
        except Exception as e:
            logger.error(f"Failed to clear memory: {e}")
    
    def render_report(self, result: ProcessingResult) -> str:
        """Render processing result as readable report."""
        return render_report(result.memory, result)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

chat_memory_service = ChatMemoryService()
