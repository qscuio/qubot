"""
Prompt Catalog - Job definitions for AI tasks.
Ported from src/services/ai/PromptCatalog.js
"""

from typing import Dict, Any, Optional, List


def truncate(value: str, max_length: int = None) -> str:
    if not value:
        return ""
    text = str(value)
    if not max_length or len(text) <= max_length:
        return text
    return text[:max_length]


def format_list(values: List[str]) -> str:
    if not values:
        return "(none)"
    return "\n".join(f"- {v}" for v in values)


JOBS = {
    "chat": {
        "id": "chat",
        "description": "General chat assistant for interactive conversations.",
        "system": """You are QuBot's professional assistant.
Be clear, accurate, and concise by default.
Ask a clarifying question when the request is ambiguous or missing key details.
Provide actionable guidance and cite assumptions when needed.
Match the user's tone without being overly casual.""",
        "build_prompt": lambda payload: str(payload.get("message", "")).strip()
    },
    
    "summarize": {
        "id": "summarize",
        "description": "Summarize text while preserving key facts and tone.",
        "system": """You are a professional summarizer.
Preserve key facts, names, numbers, and intent.
Maintain the original tone.
Do not add new information.
Output plain text only.""",
        "build_prompt": lambda payload: f"""Summarize the following text in {payload.get('maxLength', 200)} characters or less.
Be concise and capture the key points.

{truncate(payload.get('text', ''), 5000)}"""
    },
    
    "translate": {
        "id": "translate",
        "description": "Translate text between languages.",
        "system": """You are a professional translator.
Preserve meaning, tone, and formatting.
Keep proper nouns and product names unchanged unless commonly translated.
Do not translate code, commands, or URLs.
Output only the translation.""",
        "build_prompt": lambda payload: f"""Translate the following text {f"from {payload.get('sourceLanguage')} " if payload.get('sourceLanguage') else ""}to {payload.get('targetLanguage', 'the requested language')}.

Text:
{truncate(payload.get('text', ''), 6000)}"""
    },
    
    "categorize": {
        "id": "categorize",
        "description": "Categorize text into predefined categories.",
        "system": """You are a classification assistant.
Choose exactly one category from the provided list.
Return JSON only in the specified format.
If uncertain, choose the closest category and mark low confidence.""",
        "build_prompt": lambda payload: f"""Categorize the following text into one of these categories:
{format_list(payload.get('categories', []))}

Text:
{truncate(payload.get('text', ''), 2000)}

Return JSON only:
{{"category":"chosen_category","confidence":"high|medium|low","reasoning":"brief explanation"}}"""
    },
    
    "sentiment": {
        "id": "sentiment",
        "description": "Sentiment analysis with score.",
        "system": """You analyze sentiment.
Use sentiment labels: positive, negative, neutral.
Score ranges from -1 to 1 (negative to positive).
Return JSON only in the specified format.""",
        "build_prompt": lambda payload: f"""Analyze the sentiment of this text.

Text:
{truncate(payload.get('text', ''), 500)}

Return JSON only:
{{"sentiment":"positive|negative|neutral","score":-1}}"""
    },
    
    "chat_summary": {
        "id": "chat_summary",
        "description": "Short chat summary for context.",
        "system": """You summarize conversation context for future messages.
Keep it to 2-3 sentences.
Mention key topics, decisions, and open issues.
Do not include extra commentary.""",
        "build_prompt": lambda payload: f"""Summarize this conversation in 2-3 sentences:

{payload.get('messagesText', '')}"""
    },
    
    "chat_notes": {
        "id": "chat_notes",
        "description": "Structured knowledge summary for exported chats.",
        "system": """You extract all valuable knowledge from a conversation.
Do not omit important details, decisions, or action items.
Preserve names, numbers, commands, and URLs exactly.
If the conversation contains conflicting statements, list both.
Use clear section headers and bullet points.
If a section has no data, write "None".""",
        "build_prompt": lambda payload: f"""Create a structured knowledge summary with these sections:
## Summary
## Key Facts and Concepts
## Decisions and Conclusions
## Action Items and Next Steps
## Code and Commands
## References and Links
## Open Questions

Capture all valuable knowledge mentioned in the conversation.
Use bullet points inside sections, and code blocks for code/commands.

Conversation:
{truncate(payload.get('conversation', ''), 15000)}"""
    },
    
    "analysis": {
        "id": "analysis",
        "description": "General analysis with flexible output formatting.",
        "system": """You are a senior analyst.
Follow the user's instructions exactly.
If a specific format is requested, use it precisely.
If no format is specified, use sections: Summary, Analysis, Risks/Assumptions, Recommendations.
Be precise, avoid speculation, and flag uncertainty explicitly.
Do not invent facts.""",
        "build_prompt": lambda payload: payload.get("prompt") or f"""Task:
{payload.get('task', '')}

Input:
{payload.get('input', '')}"""
    },
}


def get_job_definition(job_id: str) -> Optional[Dict]:
    return JOBS.get(job_id)


def list_jobs() -> List[Dict[str, str]]:
    return [{"id": k, "description": v["description"]} for k, v in JOBS.items()]


def build_job_prompt(job_id: str, payload: Dict = None) -> Dict[str, str]:
    """Build system prompt and user prompt for a job."""
    job = get_job_definition(job_id)
    if not job:
        raise ValueError(f"Unknown AI job: {job_id}")
    
    payload = payload or {}
    prompt = job["build_prompt"](payload) if "build_prompt" in job else str(payload.get("prompt", "")).strip()
    
    if not prompt:
        raise ValueError(f"Empty prompt for AI job: {job_id}")
    
    return {
        "system": job.get("system", ""),
        "prompt": prompt
    }
