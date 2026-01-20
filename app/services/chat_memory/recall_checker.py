"""
Recall Checker - Coverage Validation

Validates that extraction didn't miss important information:
- Numbers, dates, amounts
- URLs and links
- Transition signals (disagreements, changes)
- Constraint keywords
- Task assignments
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple

from app.core.logger import Logger
from app.services.chat_memory.data_models import ChunkExtraction

logger = Logger("RecallChecker")


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage Check Patterns
# ═══════════════════════════════════════════════════════════════════════════════

COVERAGE_PATTERNS = {
    'numbers': [
        r'\d+\.?\d*\s*[%$¥€£]',           # Percentages, currencies
        r'[¥$€£]\s*\d{3,}',               # Currency amounts
        r'\d+\s*[万亿KMB]',                # Large numbers
        r'\d{4,}',                          # Long numbers (likely important)
    ],
    'dates': [
        r'\d{4}[-/年]\d{1,2}[-/月]?\d{0,2}日?',  # Full dates
        r'\d{1,2}[月号日]',                      # Partial dates
        r'(周|星期)[一二三四五六日天]',            # Days of week
        r'(今天|明天|昨天|下周|本月|下月)',        # Relative dates
    ],
    'urls': [
        r'https?://\S+',
        r'www\.\S+',
        r'[a-zA-Z0-9.-]+\.(com|org|net|io|co|cn)/\S*',
    ],
    'transitions': [
        r'但是|不过|然而|反而|相反|反例',
        r'不同意|反对|质疑|有问题',
        r'改了|撤回|取消|推翻|更正|修改',
        r'最终|最后决定|定了|确认',
    ],
    'constraints': [
        r'必须|一定要|不能|不可以|禁止',
        r'预算.{0,5}\d|上限.{0,5}\d|\d.{0,5}以内',
        r'截止|deadline|期限|最晚',
    ],
    'tasks': [
        r'我来|你来|我负责|你负责',
        r'请.{1,10}(做|完成|处理|跟进)',
        r'todo|待办|action item',
    ],
}

# Compile patterns
COMPILED_COVERAGE = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in COVERAGE_PATTERNS.items()
}


# ═══════════════════════════════════════════════════════════════════════════════
# Recall Report
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RecallReport:
    """Report on extraction coverage."""
    total_expected: int = 0
    total_captured: int = 0
    recall_score: float = 1.0
    
    # By category
    missing_numbers: List[str] = field(default_factory=list)
    missing_dates: List[str] = field(default_factory=list)
    missing_urls: List[str] = field(default_factory=list)
    missing_transitions: List[str] = field(default_factory=list)
    missing_constraints: List[str] = field(default_factory=list)
    missing_tasks: List[str] = field(default_factory=list)
    
    # Suggestions for improvement
    suggestions: List[str] = field(default_factory=list)
    
    @property
    def is_good(self) -> bool:
        """Check if recall is acceptable (≥80%)."""
        return self.recall_score >= 0.8
    
    def to_dict(self) -> Dict:
        return {
            'total_expected': self.total_expected,
            'total_captured': self.total_captured,
            'recall_score': round(self.recall_score, 3),
            'missing_numbers': self.missing_numbers[:5],
            'missing_dates': self.missing_dates[:5],
            'missing_urls': self.missing_urls[:5],
            'missing_transitions': self.missing_transitions[:5],
            'missing_constraints': self.missing_constraints[:5],
            'missing_tasks': self.missing_tasks[:5],
            'suggestions': self.suggestions,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Recall Checker
# ═══════════════════════════════════════════════════════════════════════════════

class RecallChecker:
    """
    Validates extraction coverage by checking for missed patterns.
    """
    
    def check(
        self,
        messages: List[Dict],
        extraction: ChunkExtraction,
    ) -> RecallReport:
        """
        Check recall of extraction against original messages.
        
        Args:
            messages: Original messages
            extraction: Extraction result to validate
            
        Returns:
            RecallReport with coverage analysis
        """
        report = RecallReport()
        
        # Combine all message text
        all_text = "\n".join([
            m.get('message_text', '') or m.get('text', '')
            for m in messages
        ])
        
        # Combine all extracted text (for searching)
        extracted_text = self._get_extracted_text(extraction)
        
        # Check each category
        for category, patterns in COMPILED_COVERAGE.items():
            found_in_source = set()
            found_in_extraction = set()
            
            for pattern in patterns:
                # Find in source
                for match in pattern.finditer(all_text):
                    found_in_source.add(match.group()[:50])
                
                # Find in extraction
                for match in pattern.finditer(extracted_text):
                    found_in_extraction.add(match.group()[:50])
            
            # Calculate missing
            missing = found_in_source - found_in_extraction
            
            # Store in report
            if category == 'numbers':
                report.missing_numbers = list(missing)[:10]
            elif category == 'dates':
                report.missing_dates = list(missing)[:10]
            elif category == 'urls':
                report.missing_urls = list(missing)[:10]
            elif category == 'transitions':
                report.missing_transitions = list(missing)[:10]
            elif category == 'constraints':
                report.missing_constraints = list(missing)[:10]
            elif category == 'tasks':
                report.missing_tasks = list(missing)[:10]
            
            report.total_expected += len(found_in_source)
            report.total_captured += len(found_in_source) - len(missing)
        
        # Calculate recall score
        if report.total_expected > 0:
            report.recall_score = report.total_captured / report.total_expected
        
        # Generate suggestions
        report.suggestions = self._generate_suggestions(report)
        
        # Log summary
        logger.info(
            f"📊 Recall check: {report.recall_score:.1%} "
            f"({report.total_captured}/{report.total_expected})"
        )
        
        if not report.is_good:
            logger.warn(f"⚠️ Low recall detected. Missing: {len(report.missing_numbers)} numbers, "
                       f"{len(report.missing_urls)} URLs, {len(report.missing_transitions)} transitions")
        
        return report
    
    def _get_extracted_text(self, extraction: ChunkExtraction) -> str:
        """Combine all extracted content into searchable text."""
        parts = []
        
        # Claims
        for claim in extraction.claims:
            parts.append(claim.claim)
            parts.extend(claim.reasons)
            for ev in claim.evidence:
                parts.append(ev.quote)
        
        # Decisions
        for decision in extraction.decisions:
            parts.append(decision.decision)
            for ev in decision.evidence:
                parts.append(ev.quote)
        
        # Action items
        for action in extraction.action_items:
            parts.append(action.task)
            if action.due:
                parts.append(action.due)
            for ev in action.evidence:
                parts.append(ev.quote)
        
        # Constraints
        for constraint in extraction.constraints:
            parts.append(constraint.constraint)
            for ev in constraint.evidence:
                parts.append(ev.quote)
        
        # Questions
        for question in extraction.open_questions:
            parts.append(question.question)
        
        return "\n".join(parts)
    
    def _generate_suggestions(self, report: RecallReport) -> List[str]:
        """Generate improvement suggestions based on missing items."""
        suggestions = []
        
        if report.missing_numbers:
            suggestions.append(f"Consider extracting {len(report.missing_numbers)} missed numeric values")
        
        if report.missing_urls:
            suggestions.append(f"Check for {len(report.missing_urls)} uncaptured URLs/links")
        
        if report.missing_transitions:
            suggestions.append(
                "Transition signals missed - may indicate overlooked disagreements or changes"
            )
        
        if report.missing_constraints:
            suggestions.append(
                "Constraint keywords missed - verify budget/deadline/limitation extraction"
            )
        
        if report.missing_tasks:
            suggestions.append(
                "Task assignment patterns missed - verify action item extraction"
            )
        
        return suggestions


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

recall_checker = RecallChecker()
