"""
Module 4: Opinion Extraction (LLM)

Extracts trading views from top N members' forward-looking messages.
LLM is used ONLY for understanding and abstracting - not for scoring.

Key features:
- Token-controlled (max 50 messages per user)
- Evidence binding (message indices)
- Prevents fabrication with structured output
"""

import json
import re
from typing import List, Dict, Optional, Any

from app.core.logger import Logger
from app.services.trader_influence.data_models import (
    AnnotatedMessage,
    MemberInfluence,
    ExtractedView,
    DirectionType,
    ViewOutcome,
    generate_view_id,
)
from app.services.trader_influence.prompts import (
    OPINION_EXTRACTION_SYSTEM_PROMPT,
    OPINION_EXTRACTION_PROMPT,
    format_messages_for_prompt,
)

logger = Logger("OpinionExtractor")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Max messages to send to LLM per user (token control)
MAX_MESSAGES_PER_USER = 50

# Max characters per message in prompt
MAX_CHARS_PER_MESSAGE = 200


# ═══════════════════════════════════════════════════════════════════════════════
# JSON Parsing Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_json_from_response(response: str) -> Optional[Dict]:
    """Extract JSON from LLM response, handling code blocks."""
    # Try to find JSON in code block
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = response.strip()
    
    # Clean up common issues
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warn(f"JSON parse error: {e}")
        return None


def _parse_stance(stance_str: str) -> DirectionType:
    """Parse stance string to DirectionType enum."""
    stance_lower = stance_str.lower().strip()
    if stance_lower in ('bullish', 'long', 'buy'):
        return DirectionType.BULLISH
    elif stance_lower in ('bearish', 'short', 'sell'):
        return DirectionType.BEARISH
    else:
        return DirectionType.NEUTRAL


# ═══════════════════════════════════════════════════════════════════════════════
# Opinion Extractor
# ═══════════════════════════════════════════════════════════════════════════════

class OpinionExtractor:
    """
    Extracts trading views from user messages using LLM.
    
    Only called for Top N members (controlled by InfluenceScorer).
    """
    
    def __init__(self):
        self._ai_service = None
        self.llm_calls = 0
    
    @property
    def ai_service(self):
        """Lazy load AI service."""
        if self._ai_service is None:
            from app.services.ai import ai_service
            self._ai_service = ai_service
        return self._ai_service
    
    async def extract_views(
        self,
        user_id: str,
        user_name: str,
        messages: List[AnnotatedMessage],
    ) -> List[ExtractedView]:
        """
        Extract trading views from a user's messages.
        
        Args:
            user_id: User identifier
            user_name: User display name
            messages: User's forward-looking messages
            
        Returns:
            List of ExtractedView objects
        """
        if not messages:
            return []
        
        # Filter to forward-looking messages only
        forward_msgs = [m for m in messages if m.features.is_forward_looking]
        
        if not forward_msgs:
            logger.debug(f"No forward-looking messages for {user_name}")
            return []
        
        # Format messages for prompt (with token control)
        messages_text = format_messages_for_prompt(
            forward_msgs, 
            max_messages=MAX_MESSAGES_PER_USER,
            max_chars_per_msg=MAX_CHARS_PER_MESSAGE,
        )
        
        # Build prompt
        prompt = OPINION_EXTRACTION_PROMPT.format(
            user_name=user_name,
            messages=messages_text,
        )
        
        # Call LLM
        try:
            result = await self.ai_service.quick_chat(prompt)
            self.llm_calls += 1
            
            content = result.get('content', '')
            parsed = _extract_json_from_response(content)
            
            if not parsed:
                logger.warn(f"Failed to parse LLM response for {user_name}")
                return []
            
            # Parse views
            views = self._parse_views(
                parsed, 
                user_id, 
                forward_msgs,
            )
            
            logger.info(f"📊 Extracted {len(views)} views for {user_name}")
            return views
            
        except Exception as e:
            logger.error(f"Opinion extraction failed for {user_name}: {e}")
            return []
    
    def _parse_views(
        self,
        data: Dict,
        user_id: str,
        messages: List[AnnotatedMessage],
    ) -> List[ExtractedView]:
        """Parse LLM response into ExtractedView objects."""
        views = []
        
        raw_views = data.get('views', [])
        
        for v in raw_views:
            try:
                stance = _parse_stance(v.get('stance', 'neutral'))
                target = v.get('target') or ''
                basis = v.get('basis', [])
                
                # Must have at least one basis
                if not basis:
                    continue
                
                # Get evidence messages
                message_indices = v.get('message_indices', [])
                evidence_messages = []
                first_mentioned = None
                
                for idx in message_indices:
                    if 0 <= idx < len(messages):
                        msg = messages[idx]
                        evidence_messages.append(msg.message_id)
                        if first_mentioned is None or msg.timestamp < first_mentioned:
                            first_mentioned = msg.timestamp
                
                # If no indices, use first message as evidence
                if not evidence_messages and messages:
                    evidence_messages = [messages[0].message_id]
                    first_mentioned = messages[0].timestamp
                
                view = ExtractedView(
                    view_id=generate_view_id(user_id, stance.value, target),
                    user_id=user_id,
                    stance=stance,
                    target=target,
                    basis=basis,
                    conditions=v.get('conditions', []),
                    risk_factors=v.get('risk_factors', []),
                    evidence_messages=evidence_messages,
                    first_mentioned=first_mentioned,
                )
                
                views.append(view)
                
            except Exception as e:
                logger.debug(f"Failed to parse view: {e}")
                continue
        
        return views
    
    async def extract_for_members(
        self,
        members: List[MemberInfluence],
        all_messages: List[AnnotatedMessage],
    ) -> Dict[str, List[ExtractedView]]:
        """
        Extract views for multiple members.
        
        Args:
            members: Top N members from influence scoring
            all_messages: All preprocessed messages
            
        Returns:
            Dict mapping user_id to list of extracted views
        """
        # Group messages by user
        user_messages: Dict[str, List[AnnotatedMessage]] = {}
        for msg in all_messages:
            if msg.user_id not in user_messages:
                user_messages[msg.user_id] = []
            user_messages[msg.user_id].append(msg)
        
        results = {}
        
        for member in members:
            user_msgs = user_messages.get(member.user_id, [])
            
            views = await self.extract_views(
                user_id=member.user_id,
                user_name=member.user_name,
                messages=user_msgs,
            )
            
            results[member.user_id] = views
        
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

opinion_extractor = OpinionExtractor()
