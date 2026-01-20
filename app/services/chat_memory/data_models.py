"""
Data Models for Structured Chat Extraction

Defines the core dataclasses for:
- Evidence binding (traceability)
- Claims with reasoning chains
- Decisions with status tracking
- Action items with ownership
- Constraints and assumptions
- Topic graphs for hierarchical organization
- Global memory for incremental updates
"""

from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# Enums for Status Tracking
# ═══════════════════════════════════════════════════════════════════════════════

class ClaimStatus(str, Enum):
    """Status of a claim in the knowledge graph."""
    ACTIVE = "active"           # Current, valid claim
    SUPERSEDED = "superseded"   # Replaced by newer claim
    UNCERTAIN = "uncertain"     # Needs verification
    DISPUTED = "disputed"       # Has counterarguments


class ClaimStance(str, Enum):
    """Stance/position of a claim."""
    SUPPORT = "support"
    OPPOSE = "oppose" 
    NEUTRAL = "neutral"


class DecisionStatus(str, Enum):
    """Status of a decision."""
    CONFIRMED = "confirmed"     # Firm decision
    TENTATIVE = "tentative"     # Preliminary, may change
    OVERTURNED = "overturned"   # Was changed/cancelled


class ActionStatus(str, Enum):
    """Status of an action item."""
    OPEN = "open"
    DOING = "doing"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ConstraintType(str, Enum):
    """Type of constraint."""
    BUDGET = "budget"
    DEADLINE = "deadline"
    TECHNICAL = "technical"
    SCOPE = "scope"
    RESOURCE = "resource"
    POLICY = "policy"


# ═══════════════════════════════════════════════════════════════════════════════
# Evidence Binding (Core Traceability Feature)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Evidence:
    """
    Evidence binding for traceability.
    Every claim/decision MUST have at least one evidence reference.
    """
    message_id: str                     # Original message ID or hash
    speaker: str                        # Who said it
    timestamp: str                      # When it was said
    quote: str                          # Short verbatim quote (≤100 chars)
    context: Optional[str] = None       # Surrounding context if needed
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> Evidence:
        return cls(**data)


# ═══════════════════════════════════════════════════════════════════════════════
# Core Extraction Units
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Claim:
    """
    A statement, opinion, or assertion from chat.
    
    Key principle: Every claim must have evidence binding.
    Claims without evidence go to hypothesis section.
    """
    id: str                             # Unique ID (hash-based)
    claim: str                          # One-sentence summary of the claim
    topic: str                          # Parent topic/theme
    speaker: str                        # Who made this claim
    stance: ClaimStance = ClaimStance.NEUTRAL
    
    # Reasoning chain (why this claim is made)
    reasons: List[str] = field(default_factory=list)
    
    # Traceability (REQUIRED - no claim without evidence)
    evidence: List[Evidence] = field(default_factory=list)
    
    # Context and assumptions
    assumptions: List[str] = field(default_factory=list)
    
    # Counterarguments and disputes
    counterpoints: List[str] = field(default_factory=list)
    
    # Status tracking for incremental updates
    status: ClaimStatus = ClaimStatus.ACTIVE
    superseded_by: Optional[str] = None  # ID of claim that replaced this
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['stance'] = self.stance.value
        d['status'] = self.status.value
        d['evidence'] = [e.to_dict() if isinstance(e, Evidence) else e for e in self.evidence]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> Claim:
        data = data.copy()
        data['stance'] = ClaimStance(data.get('stance', 'neutral'))
        data['status'] = ClaimStatus(data.get('status', 'active'))
        data['evidence'] = [Evidence.from_dict(e) if isinstance(e, dict) else e for e in data.get('evidence', [])]
        return cls(**data)
    
    @property
    def has_evidence(self) -> bool:
        return len(self.evidence) > 0


@dataclass
class Decision:
    """
    A decision or commitment made in chat.
    Tracks status changes (confirmed → overturned).
    """
    id: str
    decision: str                       # What was decided
    made_by: str                        # Who made the decision
    topic: str                          # Related topic
    
    # Traceability
    evidence: List[Evidence] = field(default_factory=list)
    
    # Status
    status: DecisionStatus = DecisionStatus.CONFIRMED
    overturned_reason: Optional[str] = None
    overturned_by: Optional[str] = None  # ID of decision that replaced this
    
    # Timestamps
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        d['evidence'] = [e.to_dict() if isinstance(e, Evidence) else e for e in self.evidence]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> Decision:
        data = data.copy()
        data['status'] = DecisionStatus(data.get('status', 'confirmed'))
        data['evidence'] = [Evidence.from_dict(e) if isinstance(e, dict) else e for e in data.get('evidence', [])]
        return cls(**data)


@dataclass
class ActionItem:
    """
    A follow-up task or action item.
    Tracks ownership and status progression.
    """
    id: str
    task: str                           # What needs to be done
    owner: str                          # Who is responsible
    topic: str                          # Related topic
    
    # Scheduling
    due: Optional[str] = None           # Due date if mentioned
    priority: Optional[str] = None      # high/medium/low if mentioned
    
    # Traceability
    evidence: List[Evidence] = field(default_factory=list)
    
    # Status (open → doing → done)
    status: ActionStatus = ActionStatus.OPEN
    blocked_reason: Optional[str] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        d['evidence'] = [e.to_dict() if isinstance(e, Evidence) else e for e in self.evidence]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> ActionItem:
        data = data.copy()
        data['status'] = ActionStatus(data.get('status', 'open'))
        data['evidence'] = [Evidence.from_dict(e) if isinstance(e, dict) else e for e in data.get('evidence', [])]
        return cls(**data)


@dataclass
class Constraint:
    """
    A limitation, requirement, or boundary condition.
    These are often lost in "pretty summaries" - we explicitly extract them.
    """
    id: str
    constraint: str                     # The constraint statement
    type: ConstraintType                # Type of constraint
    topic: str                          # Related topic
    
    # Whether this is a hard (must) or soft (should) constraint
    is_hard: bool = True
    
    # Traceability
    evidence: List[Evidence] = field(default_factory=list)
    
    # Validity
    is_active: bool = True
    invalidated_reason: Optional[str] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['type'] = self.type.value
        d['evidence'] = [e.to_dict() if isinstance(e, Evidence) else e for e in self.evidence]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> Constraint:
        data = data.copy()
        data['type'] = ConstraintType(data.get('type', 'scope'))
        data['evidence'] = [Evidence.from_dict(e) if isinstance(e, dict) else e for e in data.get('evidence', [])]
        return cls(**data)


@dataclass
class OpenQuestion:
    """
    An unresolved question or uncertainty.
    """
    id: str
    question: str                       # The open question
    topic: str                          # Related topic
    raised_by: str                      # Who raised it
    
    # Traceability
    evidence: List[Evidence] = field(default_factory=list)
    
    # Status
    is_resolved: bool = False
    resolution: Optional[str] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['evidence'] = [e.to_dict() if isinstance(e, Evidence) else e for e in self.evidence]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> OpenQuestion:
        data = data.copy()
        data['evidence'] = [Evidence.from_dict(e) if isinstance(e, dict) else e for e in data.get('evidence', [])]
        return cls(**data)


# ═══════════════════════════════════════════════════════════════════════════════
# Topic Organization
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TopicGraph:
    """
    Hierarchical organization of claims under a topic.
    Enables navigation: topic → claims → evidence
    """
    topic: str                          # Topic name
    summary: str                        # Brief topic summary
    
    # Claims organized by stance
    supporting_claims: List[str] = field(default_factory=list)  # Claim IDs
    opposing_claims: List[str] = field(default_factory=list)
    neutral_claims: List[str] = field(default_factory=list)
    
    # Related items
    decisions: List[str] = field(default_factory=list)          # Decision IDs
    action_items: List[str] = field(default_factory=list)       # ActionItem IDs
    constraints: List[str] = field(default_factory=list)        # Constraint IDs
    
    # Metadata
    message_count: int = 0
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> TopicGraph:
        return cls(**data)


# ═══════════════════════════════════════════════════════════════════════════════
# Chunk and Global Memory
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ChunkExtraction:
    """
    Extraction result for a single message chunk.
    Intermediate result before merging into global memory.
    """
    chunk_id: str
    channel_id: str
    channel_name: str
    
    # Time boundaries
    time_start: str
    time_end: str
    message_count: int
    
    # Detected topics in this chunk
    topics: List[str] = field(default_factory=list)
    
    # Extracted items (all with evidence binding)
    claims: List[Claim] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    action_items: List[ActionItem] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)
    
    # Hypotheses (claims without sufficient evidence)
    hypotheses: List[str] = field(default_factory=list)
    
    # Quality metrics
    evidence_coverage: float = 0.0      # % of items with evidence
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "message_count": self.message_count,
            "topics": self.topics,
            "claims": [c.to_dict() for c in self.claims],
            "decisions": [d.to_dict() for d in self.decisions],
            "action_items": [a.to_dict() for a in self.action_items],
            "constraints": [c.to_dict() for c in self.constraints],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "hypotheses": self.hypotheses,
            "evidence_coverage": self.evidence_coverage,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> ChunkExtraction:
        return cls(
            chunk_id=data["chunk_id"],
            channel_id=data["channel_id"],
            channel_name=data["channel_name"],
            time_start=data["time_start"],
            time_end=data["time_end"],
            message_count=data["message_count"],
            topics=data.get("topics", []),
            claims=[Claim.from_dict(c) for c in data.get("claims", [])],
            decisions=[Decision.from_dict(d) for d in data.get("decisions", [])],
            action_items=[ActionItem.from_dict(a) for a in data.get("action_items", [])],
            constraints=[Constraint.from_dict(c) for c in data.get("constraints", [])],
            open_questions=[OpenQuestion.from_dict(q) for q in data.get("open_questions", [])],
            hypotheses=data.get("hypotheses", []),
            evidence_coverage=data.get("evidence_coverage", 0.0),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class GlobalMemory:
    """
    Persistent knowledge graph from chat history.
    Updated incrementally via diff-merge, not rewritten each time.
    """
    channel_id: str
    channel_name: str
    
    # Topic-organized knowledge graph
    topic_graphs: Dict[str, TopicGraph] = field(default_factory=dict)
    
    # All extracted items (indexed by ID)
    claims: Dict[str, Claim] = field(default_factory=dict)
    decisions: Dict[str, Decision] = field(default_factory=dict)
    action_items: Dict[str, ActionItem] = field(default_factory=dict)
    constraints: Dict[str, Constraint] = field(default_factory=dict)
    open_questions: Dict[str, OpenQuestion] = field(default_factory=dict)
    
    # Statistics
    total_messages_processed: int = 0
    total_chunks_processed: int = 0
    
    # Version for conflict detection
    version: int = 1
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "topic_graphs": {k: v.to_dict() for k, v in self.topic_graphs.items()},
            "claims": {k: v.to_dict() for k, v in self.claims.items()},
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "action_items": {k: v.to_dict() for k, v in self.action_items.items()},
            "constraints": {k: v.to_dict() for k, v in self.constraints.items()},
            "open_questions": {k: v.to_dict() for k, v in self.open_questions.items()},
            "total_messages_processed": self.total_messages_processed,
            "total_chunks_processed": self.total_chunks_processed,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    @classmethod
    def from_dict(cls, data: Dict) -> GlobalMemory:
        return cls(
            channel_id=data["channel_id"],
            channel_name=data["channel_name"],
            topic_graphs={k: TopicGraph.from_dict(v) for k, v in data.get("topic_graphs", {}).items()},
            claims={k: Claim.from_dict(v) for k, v in data.get("claims", {}).items()},
            decisions={k: Decision.from_dict(v) for k, v in data.get("decisions", {}).items()},
            action_items={k: ActionItem.from_dict(v) for k, v in data.get("action_items", {}).items()},
            constraints={k: Constraint.from_dict(v) for k, v in data.get("constraints", {}).items()},
            open_questions={k: OpenQuestion.from_dict(v) for k, v in data.get("open_questions", {}).items()},
            total_messages_processed=data.get("total_messages_processed", 0),
            total_chunks_processed=data.get("total_chunks_processed", 0),
            version=data.get("version", 1),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
    
    @classmethod
    def create_empty(cls, channel_id: str, channel_name: str) -> GlobalMemory:
        """Create a new empty memory for a channel."""
        return cls(
            channel_id=channel_id,
            channel_name=channel_name,
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Statistics and Metrics
    # ─────────────────────────────────────────────────────────────────────────
    
    @property
    def active_claims_count(self) -> int:
        return sum(1 for c in self.claims.values() if c.status == ClaimStatus.ACTIVE)
    
    @property
    def active_decisions_count(self) -> int:
        return sum(1 for d in self.decisions.values() if d.status == DecisionStatus.CONFIRMED)
    
    @property
    def open_actions_count(self) -> int:
        return sum(1 for a in self.action_items.values() if a.status in (ActionStatus.OPEN, ActionStatus.DOING))
    
    @property
    def active_constraints_count(self) -> int:
        return sum(1 for c in self.constraints.values() if c.is_active)
    
    @property
    def traceability_score(self) -> float:
        """Calculate % of items with evidence binding."""
        total = len(self.claims) + len(self.decisions) + len(self.action_items) + len(self.constraints)
        if total == 0:
            return 1.0
        
        with_evidence = sum(1 for c in self.claims.values() if c.has_evidence)
        with_evidence += sum(1 for d in self.decisions.values() if d.evidence)
        with_evidence += sum(1 for a in self.action_items.values() if a.evidence)
        with_evidence += sum(1 for c in self.constraints.values() if c.evidence)
        
        return with_evidence / total


# ═══════════════════════════════════════════════════════════════════════════════
# Processing Result
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProcessingResult:
    """
    Result of processing a batch of messages.
    Contains the updated memory and quality metrics.
    """
    memory: GlobalMemory
    
    # What was processed
    chunks_processed: int
    messages_processed: int
    
    # What was extracted
    new_claims: int
    new_decisions: int
    new_actions: int
    new_constraints: int
    
    # Merge statistics
    merged_claims: int = 0              # Claims with merged evidence
    superseded_claims: int = 0          # Claims marked as superseded
    conflicts_detected: int = 0         # Claims with conflicts
    
    # Quality metrics
    hard_fact_recall: float = 0.0       # % of numbers/dates captured
    traceability: float = 0.0           # % of items with evidence
    
    # Timing
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "chunks_processed": self.chunks_processed,
            "messages_processed": self.messages_processed,
            "new_claims": self.new_claims,
            "new_decisions": self.new_decisions,
            "new_actions": self.new_actions,
            "new_constraints": self.new_constraints,
            "merged_claims": self.merged_claims,
            "superseded_claims": self.superseded_claims,
            "conflicts_detected": self.conflicts_detected,
            "hard_fact_recall": self.hard_fact_recall,
            "traceability": self.traceability,
            "processing_time_ms": self.processing_time_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════

def generate_id(content: str, prefix: str = "") -> str:
    """Generate a unique ID from content hash."""
    hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"{prefix}{hash_val}" if prefix else hash_val


def generate_claim_id(claim_text: str, speaker: str) -> str:
    """Generate unique claim ID."""
    return generate_id(f"{speaker}:{claim_text}", "clm_")


def generate_decision_id(decision_text: str, made_by: str) -> str:
    """Generate unique decision ID."""
    return generate_id(f"{made_by}:{decision_text}", "dec_")


def generate_action_id(task: str, owner: str) -> str:
    """Generate unique action item ID."""
    return generate_id(f"{owner}:{task}", "act_")


def generate_constraint_id(constraint: str) -> str:
    """Generate unique constraint ID."""
    return generate_id(constraint, "cst_")


def generate_question_id(question: str) -> str:
    """Generate unique question ID."""
    return generate_id(question, "qst_")
