"""
Memory Merger - Diff-based Global Memory Updates

Handles incremental updates to global memory:
- New items: Add to memory
- Duplicate claims: Merge evidence lists
- Conflicting claims: Keep both, mark as disputed
- Overturned decisions: Mark as superseded
- Action items: Update status (open→doing→done)
"""

from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set

from app.core.logger import Logger
from app.services.chat_memory.data_models import (
    Claim,
    Decision,
    ActionItem,
    Constraint,
    OpenQuestion,
    TopicGraph,
    ChunkExtraction,
    GlobalMemory,
    ClaimStatus,
    ClaimStance,
    DecisionStatus,
    ActionStatus,
)

logger = Logger("MemoryMerger")


# ═══════════════════════════════════════════════════════════════════════════════
# Similarity Detection
# ═══════════════════════════════════════════════════════════════════════════════

def text_similarity(text1: str, text2: str) -> float:
    """
    Simple text similarity based on word overlap (Jaccard).
    Returns 0.0-1.0.
    """
    if not text1 or not text2:
        return 0.0
    
    # Tokenize (simple split + lowercase)
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0


def find_similar_claim(
    claim: Claim, 
    existing_claims: Dict[str, Claim],
    threshold: float = 0.6
) -> Optional[Tuple[str, float]]:
    """Find the most similar existing claim if above threshold."""
    best_id = None
    best_score = 0.0
    
    for existing_id, existing_claim in existing_claims.items():
        # Same topic required for high similarity
        if claim.topic and existing_claim.topic and claim.topic != existing_claim.topic:
            continue
        
        score = text_similarity(claim.claim, existing_claim.claim)
        if score > best_score and score >= threshold:
            best_score = score
            best_id = existing_id
    
    return (best_id, best_score) if best_id else None


def find_similar_decision(
    decision: Decision,
    existing_decisions: Dict[str, Decision],
    threshold: float = 0.6
) -> Optional[Tuple[str, float]]:
    """Find similar existing decision."""
    best_id = None
    best_score = 0.0
    
    for existing_id, existing_dec in existing_decisions.items():
        score = text_similarity(decision.decision, existing_dec.decision)
        if score > best_score and score >= threshold:
            best_score = score
            best_id = existing_id
    
    return (best_id, best_score) if best_id else None


# ═══════════════════════════════════════════════════════════════════════════════
# Memory Merger
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryMerger:
    """
    Diff-based memory merger.
    
    Merge rules:
    1. New claim → Add to memory
    2. Duplicate claim → Merge evidence lists
    3. Conflicting claim (same topic, different stance) → Mark both as disputed
    4. Overturned decision → Mark old as superseded
    5. Action item update → Update status
    """
    
    def __init__(self, similarity_threshold: float = 0.6):
        self.similarity_threshold = similarity_threshold
    
    def merge(
        self,
        extraction: ChunkExtraction,
        memory: GlobalMemory,
    ) -> Tuple[GlobalMemory, Dict[str, int]]:
        """
        Merge extraction into global memory.
        
        Args:
            extraction: New chunk extraction to merge
            memory: Existing global memory
            
        Returns:
            (updated_memory, merge_stats)
        """
        stats = {
            'new_claims': 0,
            'merged_claims': 0,
            'disputed_claims': 0,
            'superseded_claims': 0,
            'new_decisions': 0,
            'superseded_decisions': 0,
            'new_actions': 0,
            'updated_actions': 0,
            'new_constraints': 0,
            'new_questions': 0,
        }
        
        # Merge claims
        for claim in extraction.claims:
            self._merge_claim(claim, memory, stats)
        
        # Merge decisions
        for decision in extraction.decisions:
            self._merge_decision(decision, memory, stats)
        
        # Merge action items
        for action in extraction.action_items:
            self._merge_action(action, memory, stats)
        
        # Merge constraints
        for constraint in extraction.constraints:
            self._merge_constraint(constraint, memory, stats)
        
        # Merge open questions
        for question in extraction.open_questions:
            self._merge_question(question, memory, stats)
        
        # Update topic graphs
        self._update_topic_graphs(extraction, memory)
        
        # Update memory metadata
        memory.total_messages_processed += extraction.message_count
        memory.total_chunks_processed += 1
        memory.version += 1
        memory.updated_at = datetime.now().isoformat()
        
        logger.info(
            f"📝 Merged into {memory.channel_name}: "
            f"+{stats['new_claims']} claims, "
            f"+{stats['new_decisions']} decisions, "
            f"+{stats['new_actions']} actions, "
            f"{stats['merged_claims']} merged, "
            f"{stats['disputed_claims']} disputes"
        )
        
        return memory, stats
    
    def _merge_claim(self, claim: Claim, memory: GlobalMemory, stats: Dict):
        """Merge a single claim into memory."""
        # Check for similar existing claim
        similar = find_similar_claim(claim, memory.claims, self.similarity_threshold)
        
        if similar:
            existing_id, score = similar
            existing = memory.claims[existing_id]
            
            # Check for conflict (same topic, opposite stance)
            if (existing.stance != claim.stance and 
                existing.stance != ClaimStance.NEUTRAL and 
                claim.stance != ClaimStance.NEUTRAL):
                # Mark both as disputed
                existing.status = ClaimStatus.DISPUTED
                existing.counterpoints.append(claim.claim)
                claim.status = ClaimStatus.DISPUTED
                claim.counterpoints.append(existing.claim)
                memory.claims[claim.id] = claim
                stats['disputed_claims'] += 1
                logger.debug(f"Conflict detected: {existing.claim[:50]} vs {claim.claim[:50]}")
            else:
                # Merge evidence
                existing.evidence.extend(claim.evidence)
                existing.reasons.extend([r for r in claim.reasons if r not in existing.reasons])
                existing.updated_at = datetime.now().isoformat()
                stats['merged_claims'] += 1
        else:
            # New claim
            memory.claims[claim.id] = claim
            stats['new_claims'] += 1
    
    def _merge_decision(self, decision: Decision, memory: GlobalMemory, stats: Dict):
        """Merge a decision into memory."""
        # Check for similar existing decision
        similar = find_similar_decision(decision, memory.decisions, self.similarity_threshold)
        
        if similar:
            existing_id, score = similar
            existing = memory.decisions[existing_id]
            
            # Check if this is an update/overturn
            if decision.status == DecisionStatus.OVERTURNED:
                # Mark existing as overturned
                existing.status = DecisionStatus.OVERTURNED
                existing.overturned_by = decision.id
                existing.overturned_reason = "Superseded by newer decision"
                existing.updated_at = datetime.now().isoformat()
                memory.decisions[decision.id] = decision
                stats['superseded_decisions'] += 1
            else:
                # Merge evidence
                existing.evidence.extend(decision.evidence)
                existing.updated_at = datetime.now().isoformat()
        else:
            # New decision
            memory.decisions[decision.id] = decision
            stats['new_decisions'] += 1
    
    def _merge_action(self, action: ActionItem, memory: GlobalMemory, stats: Dict):
        """Merge an action item into memory."""
        # Check if this action already exists
        if action.id in memory.action_items:
            existing = memory.action_items[action.id]
            
            # Update status if progressed
            status_order = [ActionStatus.OPEN, ActionStatus.DOING, ActionStatus.DONE, ActionStatus.BLOCKED, ActionStatus.CANCELLED]
            existing_idx = status_order.index(existing.status) if existing.status in status_order else 0
            new_idx = status_order.index(action.status) if action.status in status_order else 0
            
            if new_idx > existing_idx:
                existing.status = action.status
                existing.updated_at = datetime.now().isoformat()
                stats['updated_actions'] += 1
            
            # Merge evidence
            existing.evidence.extend(action.evidence)
        else:
            # Check for similar by task description
            for existing_id, existing in memory.action_items.items():
                if text_similarity(action.task, existing.task) > self.similarity_threshold:
                    # Merge with existing
                    existing.evidence.extend(action.evidence)
                    if action.due and not existing.due:
                        existing.due = action.due
                    existing.updated_at = datetime.now().isoformat()
                    stats['updated_actions'] += 1
                    return
            
            # New action
            memory.action_items[action.id] = action
            stats['new_actions'] += 1
    
    def _merge_constraint(self, constraint: Constraint, memory: GlobalMemory, stats: Dict):
        """Merge a constraint into memory."""
        # Check for existing similar constraint
        for existing_id, existing in memory.constraints.items():
            if text_similarity(constraint.constraint, existing.constraint) > self.similarity_threshold:
                # Merge evidence
                existing.evidence.extend(constraint.evidence)
                return
        
        # New constraint
        memory.constraints[constraint.id] = constraint
        stats['new_constraints'] += 1
    
    def _merge_question(self, question: OpenQuestion, memory: GlobalMemory, stats: Dict):
        """Merge an open question into memory."""
        # Check for existing similar question
        for existing_id, existing in memory.open_questions.items():
            if text_similarity(question.question, existing.question) > self.similarity_threshold:
                # Merge evidence
                existing.evidence.extend(question.evidence)
                return
        
        # New question
        memory.open_questions[question.id] = question
        stats['new_questions'] += 1
    
    def _update_topic_graphs(self, extraction: ChunkExtraction, memory: GlobalMemory):
        """Update topic graphs with new extraction data."""
        for topic in extraction.topics:
            if not topic:
                continue
            
            if topic not in memory.topic_graphs:
                memory.topic_graphs[topic] = TopicGraph(
                    topic=topic,
                    summary=f"Discussion about {topic}",
                )
            
            graph = memory.topic_graphs[topic]
            graph.message_count += extraction.message_count
            graph.last_activity = datetime.now().isoformat()
            
            # Add claim IDs to topic
            for claim in extraction.claims:
                if claim.topic == topic or not claim.topic:
                    if claim.stance == ClaimStance.SUPPORT:
                        if claim.id not in graph.supporting_claims:
                            graph.supporting_claims.append(claim.id)
                    elif claim.stance == ClaimStance.OPPOSE:
                        if claim.id not in graph.opposing_claims:
                            graph.opposing_claims.append(claim.id)
                    else:
                        if claim.id not in graph.neutral_claims:
                            graph.neutral_claims.append(claim.id)
            
            # Add decision IDs
            for decision in extraction.decisions:
                if decision.topic == topic or not decision.topic:
                    if decision.id not in graph.decisions:
                        graph.decisions.append(decision.id)
            
            # Add action item IDs
            for action in extraction.action_items:
                if action.topic == topic or not action.topic:
                    if action.id not in graph.action_items:
                        graph.action_items.append(action.id)
            
            # Add constraint IDs
            for constraint in extraction.constraints:
                if constraint.topic == topic or not constraint.topic:
                    if constraint.id not in graph.constraints:
                        graph.constraints.append(constraint.id)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

memory_merger = MemoryMerger()
