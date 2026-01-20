"""
Structured Information Extractor

Two-pass extraction with key sentence pre-filtering:
- Pass 1: Hard info (facts, decisions, numbers, links, constraints)
- Pass 2: Soft info (opinions, reasoning, disagreements)

Key features:
- Evidence binding for every extracted item
- Heuristic pre-filtering to improve recall
- Structured JSON output parsing
"""

import re
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple

from app.core.logger import Logger
from app.services.chat_memory.data_models import (
    Evidence,
    Claim,
    Decision,
    ActionItem,
    Constraint,
    OpenQuestion,
    ChunkExtraction,
    ClaimStatus,
    ClaimStance,
    DecisionStatus,
    ActionStatus,
    ConstraintType,
    generate_claim_id,
    generate_decision_id,
    generate_action_id,
    generate_constraint_id,
    generate_question_id,
)
from app.services.chat_memory.chunker import MessageChunk
from app.services.chat_memory.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    HARD_INFO_EXTRACTION_PROMPT,
    SOFT_INFO_EXTRACTION_PROMPT,
)

logger = Logger("Extractor")


# ═══════════════════════════════════════════════════════════════════════════════
# Key Sentence Pre-filtering (Heuristic-based)
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns for high-value sentences (improves AI recall)
HIGH_VALUE_PATTERNS = {
    'numbers': [
        r'\d+\.?\d*\s*[%$¥€£]',           # Percentages, currencies
        r'[¥$€£]\s*\d+',                   # Currency prefix
        r'\d+\s*[万亿KMB]',                # Large numbers
        r'\d{4}[-/年]\d{1,2}[-/月]?\d{0,2}', # Dates
        r'\d{1,2}[：:]\d{2}',              # Times
    ],
    'decisions': [
        r'决定|确定|最终|结论|定了|就这样|敲定',
        r'we decided|agreed|concluded|settled|final',
    ],
    'tasks': [
        r'我来|你来|我负责|你负责|待办|todo|action item',
        r'请.{1,10}(做|完成|处理|跟进)',
        r'截止|deadline|due|by\s+\d',
    ],
    'constraints': [
        r'必须|一定要|不能|不要|不可以|禁止',
        r'预算|上限|下限|最多|最少|期限',
        r'must|cannot|should not|limit|budget|max|min',
    ],
    'transitions': [
        r'但是|不过|然而|反而|相反|反例',
        r'不同意|反对|质疑|有问题|存疑',
        r'改了|撤回|取消|推翻|更正',
        r'however|but|although|disagree|contrary',
    ],
    'links': [
        r'https?://\S+',
        r'github\.com|notion\.so|figma\.com|docs\.google',
    ],
}

# Compile patterns
COMPILED_PATTERNS = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in HIGH_VALUE_PATTERNS.items()
}


def categorize_sentence(text: str) -> List[str]:
    """Categorize a sentence by high-value pattern matches."""
    categories = []
    for category, patterns in COMPILED_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                categories.append(category)
                break
    return categories


def highlight_key_sentences(messages: List[Dict]) -> Tuple[str, List[str]]:
    """
    Pre-filter and highlight key sentences for AI.
    Returns (formatted_text, highlighted_indices).
    """
    lines = []
    highlights = []
    
    for msg in messages:
        text = msg.get('message_text', '') or msg.get('text', '')
        sender = msg.get('sender_name', '') or msg.get('sender', 'Unknown')
        timestamp = msg.get('created_at', '') or msg.get('timestamp', '')
        
        if isinstance(timestamp, datetime):
            time_str = timestamp.strftime('%H:%M')
        elif isinstance(timestamp, str) and 'T' in timestamp:
            time_str = timestamp.split('T')[1][:5]
        else:
            time_str = str(timestamp)[:5] if timestamp else ''
        
        # Check for high-value patterns
        categories = categorize_sentence(text)
        
        if categories:
            # Mark as highlighted
            prefix = f"⭐[{','.join(categories)}] "
            highlights.append(text[:50])
        else:
            prefix = ""
        
        lines.append(f"[{time_str}] {sender}: {prefix}{text}")
    
    return "\n".join(lines), highlights


# ═══════════════════════════════════════════════════════════════════════════════
# JSON Parsing Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def extract_json_from_response(response: str) -> Optional[Dict]:
    """Extract JSON from AI response, handling markdown code blocks."""
    # Try to find JSON in code block
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try direct JSON
        json_str = response.strip()
    
    # Clean up common issues
    json_str = re.sub(r',\s*}', '}', json_str)  # Trailing commas
    json_str = re.sub(r',\s*]', ']', json_str)  # Trailing commas in arrays
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warn(f"JSON parse error: {e}")
        logger.debug(f"Raw response: {response[:500]}")
        return None


def parse_evidence(data: Dict) -> Optional[Evidence]:
    """Parse evidence dict into Evidence object."""
    if not data or not data.get('quote'):
        return None
    
    return Evidence(
        message_id=hashlib.md5(data.get('quote', '').encode()).hexdigest()[:8],
        speaker=data.get('speaker', 'Unknown'),
        timestamp=data.get('time', ''),
        quote=data.get('quote', '')[:100],  # Limit quote length
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Extractor Service
# ═══════════════════════════════════════════════════════════════════════════════

class Extractor:
    """
    Two-pass structured information extractor.
    
    Pass 1: Hard info (facts, decisions, numbers, links)
    Pass 2: Soft info (opinions, reasoning, disagreements)
    """
    
    def __init__(self):
        self._ai_service = None
    
    @property
    def ai_service(self):
        """Lazy load AI service."""
        if self._ai_service is None:
            from app.services.ai import ai_service
            self._ai_service = ai_service
        return self._ai_service
    
    async def extract(
        self,
        chunk: MessageChunk,
        channel_id: str,
        channel_name: str,
    ) -> ChunkExtraction:
        """
        Extract structured information from a message chunk.
        
        Args:
            chunk: MessageChunk to process
            channel_id: Channel identifier
            channel_name: Channel display name
            
        Returns:
            ChunkExtraction with all extracted items
        """
        # Prepare message text with highlights
        messages_text = chunk.get_text_for_extraction()
        
        # Run two-pass extraction
        hard_info = await self._extract_hard_info(messages_text)
        soft_info = await self._extract_soft_info(messages_text)
        
        # Build ChunkExtraction
        extraction = self._build_extraction(
            chunk=chunk,
            channel_id=channel_id,
            channel_name=channel_name,
            hard_info=hard_info,
            soft_info=soft_info,
        )
        
        logger.info(
            f"📊 Extracted from chunk {chunk.chunk_id}: "
            f"{len(extraction.claims)} claims, "
            f"{len(extraction.decisions)} decisions, "
            f"{len(extraction.action_items)} actions, "
            f"{len(extraction.constraints)} constraints"
        )
        
        return extraction
    
    async def _extract_hard_info(self, messages_text: str) -> Dict:
        """Pass 1: Extract hard/factual information."""
        prompt = HARD_INFO_EXTRACTION_PROMPT.format(messages=messages_text)
        
        try:
            result = await self.ai_service.quick_chat(prompt)
            content = result.get('content', '')
            parsed = extract_json_from_response(content)
            return parsed or {}
        except Exception as e:
            logger.error(f"Hard info extraction failed: {e}")
            return {}
    
    async def _extract_soft_info(self, messages_text: str) -> Dict:
        """Pass 2: Extract soft/opinion information."""
        prompt = SOFT_INFO_EXTRACTION_PROMPT.format(messages=messages_text)
        
        try:
            result = await self.ai_service.quick_chat(prompt)
            content = result.get('content', '')
            parsed = extract_json_from_response(content)
            return parsed or {}
        except Exception as e:
            logger.error(f"Soft info extraction failed: {e}")
            return {}
    
    def _build_extraction(
        self,
        chunk: MessageChunk,
        channel_id: str,
        channel_name: str,
        hard_info: Dict,
        soft_info: Dict,
    ) -> ChunkExtraction:
        """Build ChunkExtraction from raw extraction results."""
        
        # Parse decisions
        decisions = []
        for d in hard_info.get('decisions', []):
            evidence = parse_evidence(d.get('evidence', {}))
            if not evidence:
                continue  # Skip without evidence
            
            decisions.append(Decision(
                id=generate_decision_id(d.get('decision', ''), d.get('made_by', '')),
                decision=d.get('decision', ''),
                made_by=d.get('made_by', 'Unknown'),
                topic='',  # Will be assigned during merge
                evidence=[evidence],
                status=DecisionStatus.CONFIRMED if d.get('status') == 'confirmed' else DecisionStatus.TENTATIVE,
                timestamp=evidence.timestamp,
            ))
        
        # Parse action items
        action_items = []
        for a in hard_info.get('action_items', []):
            evidence = parse_evidence(a.get('evidence', {}))
            if not evidence:
                continue
            
            action_items.append(ActionItem(
                id=generate_action_id(a.get('task', ''), a.get('owner', '')),
                task=a.get('task', ''),
                owner=a.get('owner', 'Unknown'),
                topic='',
                due=a.get('due'),
                priority=a.get('priority'),
                evidence=[evidence],
                status=ActionStatus.OPEN,
            ))
        
        # Parse constraints
        constraints = []
        for c in hard_info.get('constraints', []):
            evidence = parse_evidence(c.get('evidence', {}))
            if not evidence:
                continue
            
            # Map constraint type
            type_map = {
                'budget': ConstraintType.BUDGET,
                'deadline': ConstraintType.DEADLINE,
                'technical': ConstraintType.TECHNICAL,
                'scope': ConstraintType.SCOPE,
                'policy': ConstraintType.POLICY,
                'resource': ConstraintType.RESOURCE,
            }
            constraint_type = type_map.get(c.get('type', 'scope'), ConstraintType.SCOPE)
            
            constraints.append(Constraint(
                id=generate_constraint_id(c.get('constraint', '')),
                constraint=c.get('constraint', ''),
                type=constraint_type,
                topic='',
                is_hard=c.get('is_hard', True),
                evidence=[evidence],
            ))
        
        # Parse claims from soft info
        claims = []
        for cl in soft_info.get('claims', []):
            evidence = parse_evidence(cl.get('evidence', {}))
            if not evidence:
                continue
            
            # Map stance
            stance_map = {
                'support': ClaimStance.SUPPORT,
                'oppose': ClaimStance.OPPOSE,
                'neutral': ClaimStance.NEUTRAL,
            }
            stance = stance_map.get(cl.get('stance', 'neutral'), ClaimStance.NEUTRAL)
            
            # Map status
            status = ClaimStatus.UNCERTAIN if cl.get('status') == 'uncertain' else ClaimStatus.ACTIVE
            
            claims.append(Claim(
                id=generate_claim_id(cl.get('claim', ''), cl.get('speaker', '')),
                claim=cl.get('claim', ''),
                topic='',  # Will be assigned
                speaker=cl.get('speaker', 'Unknown'),
                stance=stance,
                reasons=cl.get('reasons', []),
                evidence=[evidence],
                assumptions=cl.get('assumptions', []),
                status=status,
            ))
        
        # Parse disagreements as claims with counterpoints
        for dis in soft_info.get('disagreements', []):
            topic = dis.get('topic', '')
            
            # Position A
            pos_a = dis.get('position_a', {})
            evidence_a = parse_evidence(pos_a.get('evidence', {}))
            if evidence_a:
                claims.append(Claim(
                    id=generate_claim_id(pos_a.get('claim', ''), pos_a.get('speaker', '')),
                    claim=pos_a.get('claim', ''),
                    topic=topic,
                    speaker=pos_a.get('speaker', 'Unknown'),
                    stance=ClaimStance.SUPPORT,
                    evidence=[evidence_a],
                    counterpoints=[dis.get('position_b', {}).get('claim', '')],
                    status=ClaimStatus.DISPUTED,
                ))
            
            # Position B
            pos_b = dis.get('position_b', {})
            evidence_b = parse_evidence(pos_b.get('evidence', {}))
            if evidence_b:
                claims.append(Claim(
                    id=generate_claim_id(pos_b.get('claim', ''), pos_b.get('speaker', '')),
                    claim=pos_b.get('claim', ''),
                    topic=topic,
                    speaker=pos_b.get('speaker', 'Unknown'),
                    stance=ClaimStance.OPPOSE,
                    evidence=[evidence_b],
                    counterpoints=[pos_a.get('claim', '')],
                    status=ClaimStatus.DISPUTED,
                ))
        
        # Parse open questions
        open_questions = []
        for q in soft_info.get('open_questions', []):
            evidence = parse_evidence(q.get('evidence', {}))
            if not evidence:
                continue
            
            open_questions.append(OpenQuestion(
                id=generate_question_id(q.get('question', '')),
                question=q.get('question', ''),
                topic='',
                raised_by=q.get('raised_by', 'Unknown'),
                evidence=[evidence],
            ))
        
        # Get topics
        topics = soft_info.get('topics', [])
        if isinstance(topics, list) and topics and isinstance(topics[0], dict):
            topics = [t.get('name', '') for t in topics]
        
        # Get hypotheses (claims without evidence)
        hypotheses = soft_info.get('hypotheses', [])
        
        # Calculate evidence coverage
        total_items = len(decisions) + len(action_items) + len(constraints) + len(claims) + len(open_questions)
        items_with_evidence = sum([
            sum(1 for d in decisions if d.evidence),
            sum(1 for a in action_items if a.evidence),
            sum(1 for c in constraints if c.evidence),
            sum(1 for cl in claims if cl.evidence),
            sum(1 for q in open_questions if q.evidence),
        ])
        evidence_coverage = items_with_evidence / total_items if total_items > 0 else 1.0
        
        return ChunkExtraction(
            chunk_id=chunk.chunk_id,
            channel_id=channel_id,
            channel_name=channel_name,
            time_start=chunk.time_start.isoformat() if chunk.time_start else '',
            time_end=chunk.time_end.isoformat() if chunk.time_end else '',
            message_count=chunk.message_count,
            topics=topics,
            claims=claims,
            decisions=decisions,
            action_items=action_items,
            constraints=constraints,
            open_questions=open_questions,
            hypotheses=hypotheses,
            evidence_coverage=evidence_coverage,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

extractor = Extractor()
