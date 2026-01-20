"""
Chat Memory Service - Structured Information Extraction Pipeline

This module implements a traceable, structured extraction pipeline for chat messages.
Instead of generating "pretty summaries", it extracts:
- Claims with evidence binding
- Decisions with status tracking
- Action items with ownership
- Constraints and assumptions

Architecture:
    Raw Messages → Topic Chunking → Extraction → Merge → Structured Memory
"""

from app.services.chat_memory.data_models import (
    Evidence,
    Claim,
    Decision,
    ActionItem,
    Constraint,
    OpenQuestion,
    TopicGraph,
    ChunkExtraction,
    GlobalMemory,
    ProcessingResult,
)
from app.services.chat_memory.service import ChatMemoryService, chat_memory_service

__all__ = [
    # Data models
    "Evidence",
    "Claim", 
    "Decision",
    "ActionItem",
    "Constraint",
    "OpenQuestion",
    "TopicGraph",
    "ChunkExtraction",
    "GlobalMemory",
    "ProcessingResult",
    # Service
    "ChatMemoryService",
    "chat_memory_service",
]
