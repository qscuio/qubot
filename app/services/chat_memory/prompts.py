"""
Extraction Prompts for Structured Information Extraction

Contains carefully crafted prompts for:
- Hard info extraction (facts, decisions, numbers, links)
- Soft info extraction (opinions, reasoning, disagreements)
- Evidence binding requirements
- Output format specifications
"""

# ═══════════════════════════════════════════════════════════════════════════════
# System Prompts
# ═══════════════════════════════════════════════════════════════════════════════

EXTRACTION_SYSTEM_PROMPT = """你是一个专业的信息抽取助手。你的任务是从群聊消息中提取结构化信息。

核心原则：
1. 【可追溯性】每条提取的信息必须绑定证据（原文引用或消息ID）
2. 【宁多勿漏】宁可多抽取，不要遗漏关键信息
3. 【不确定标记】不确定的信息标记为 uncertain，不要编造
4. 【保留冲突】如有分歧/反对意见，保留双方观点，不要只保留一方

你必须严格按照指定的JSON格式输出，不要添加任何额外的解释文字。"""


# ═══════════════════════════════════════════════════════════════════════════════
# Hard Info Extraction (Pass 1)
# ═══════════════════════════════════════════════════════════════════════════════

HARD_INFO_EXTRACTION_PROMPT = """从以下群聊消息中提取"硬信息"（事实性内容）：

【要提取的内容】
1. 决策/决定：明确做出的决定（谁决定了什么）
2. 数字/数据：价格、百分比、金额、日期、时间、数量
3. 行动项/TODO：需要后续执行的任务（谁负责什么，截止时间）
4. 链接/资源：提到的URL、文件、工具、资源
5. 约束条件：预算、期限、技术限制、政策要求

【消息记录】
{messages}

【输出格式】严格按以下JSON格式输出：
```json
{{
  "decisions": [
    {{
      "decision": "决定的内容（一句话）",
      "made_by": "决策者",
      "status": "confirmed|tentative",
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用（≤80字）",
        "time": "HH:MM"
      }}
    }}
  ],
  "action_items": [
    {{
      "task": "任务描述",
      "owner": "负责人",
      "due": "截止时间（如有）",
      "priority": "high|medium|low",
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用",
        "time": "HH:MM"
      }}
    }}
  ],
  "data_points": [
    {{
      "type": "number|date|price|percentage|amount",
      "value": "具体值",
      "context": "这个数字代表什么",
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用",
        "time": "HH:MM"
      }}
    }}
  ],
  "resources": [
    {{
      "type": "url|file|tool|document",
      "name": "资源名称",
      "url": "链接（如有）",
      "description": "简要说明",
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用",
        "time": "HH:MM"
      }}
    }}
  ],
  "constraints": [
    {{
      "constraint": "约束内容",
      "type": "budget|deadline|technical|scope|policy|resource",
      "is_hard": true,
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用",
        "time": "HH:MM"
      }}
    }}
  ]
}}
```

注意：
- 没有相关内容的字段返回空数组 []
- evidence 字段必填，没有证据的信息不要提取
- quote 必须是消息中的原文，不要改写"""


# ═══════════════════════════════════════════════════════════════════════════════
# Soft Info Extraction (Pass 2)
# ═══════════════════════════════════════════════════════════════════════════════

SOFT_INFO_EXTRACTION_PROMPT = """从以下群聊消息中提取"软信息"（观点性内容）：

【要提取的内容】
1. 观点/主张：某人提出的看法、判断、预测
2. 论据/理由：支持观点的逻辑、论证、例子
3. 分歧/反对：不同意见、质疑、反例
4. 假设/前提：隐含的前提条件、假设
5. 未解决问题：悬而未决的疑问

【消息记录】
{messages}

【输出格式】严格按以下JSON格式输出：
```json
{{
  "topics": ["识别出的主要话题1", "话题2"],
  "claims": [
    {{
      "claim": "观点内容（一句话总结）",
      "speaker": "提出者",
      "stance": "support|oppose|neutral",
      "reasons": ["理由1", "理由2"],
      "assumptions": ["隐含假设（如有）"],
      "status": "active|uncertain",
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用（≤80字）",
        "time": "HH:MM"
      }}
    }}
  ],
  "disagreements": [
    {{
      "topic": "争议话题",
      "position_a": {{
        "claim": "观点A",
        "speaker": "持有者A",
        "evidence": {{"speaker": "", "quote": "", "time": ""}}
      }},
      "position_b": {{
        "claim": "观点B", 
        "speaker": "持有者B",
        "evidence": {{"speaker": "", "quote": "", "time": ""}}
      }},
      "resolved": false,
      "resolution": null
    }}
  ],
  "open_questions": [
    {{
      "question": "未解决的问题",
      "raised_by": "提问者",
      "evidence": {{
        "speaker": "原话说话人",
        "quote": "原文引用",
        "time": "HH:MM"
      }}
    }}
  ],
  "hypotheses": [
    "缺乏证据但值得记录的猜测（无evidence字段的观点放这里）"
  ]
}}
```

注意：
- 重点关注带有"但是/不过/反例/不同意/改了/撤回"等转折词的内容
- 观点和分歧都要保留，不要只保留获胜方
- 假设(assumptions)是指没有明确说出但逻辑上必须成立的前提"""


# ═══════════════════════════════════════════════════════════════════════════════
# Merge and Update Prompts
# ═══════════════════════════════════════════════════════════════════════════════

MERGE_CLAIMS_PROMPT = """对比新提取的观点和现有记忆，执行合并操作：

【现有观点】
{existing_claims}

【新提取观点】
{new_claims}

【合并规则】
1. 完全相同的观点：合并证据列表
2. 同一话题但不同观点：标记为 disputed
3. 推翻了旧观点的新观点：旧观点标记为 superseded
4. 全新的观点：直接添加

【输出格式】
```json
{{
  "merged": [
    {{
      "id": "原观点ID",
      "action": "keep|merge_evidence|mark_superseded|mark_disputed",
      "merge_with": "新观点index（如果是merge）",
      "superseded_by": "新观点index（如果是superseded）"
    }}
  ],
  "new": [0, 2, 5],
  "conflicts": [
    {{
      "existing_id": "冲突的现有观点ID",
      "new_index": 1,
      "reason": "冲突原因"
    }}
  ]
}}
```"""


# ═══════════════════════════════════════════════════════════════════════════════
# Topic Detection
# ═══════════════════════════════════════════════════════════════════════════════

TOPIC_DETECTION_PROMPT = """识别以下消息讨论的主要话题（1-5个）：

【消息记录】
{messages}

【输出格式】
```json
{{
  "topics": [
    {{
      "name": "话题名称（简短）",
      "summary": "一句话概括",
      "message_count": 10
    }}
  ]
}}
```

注意：话题名称要简洁，如"产品定价"、"技术选型"、"团队分工"等"""


# ═══════════════════════════════════════════════════════════════════════════════
# Report Generation
# ═══════════════════════════════════════════════════════════════════════════════

GENERATE_REPORT_PROMPT = """基于以下结构化信息生成群聊日报：

【频道】{channel_name}
【日期】{date}
【统计】消息 {message_count} 条 | 话题 {topic_count} 个 | 决策 {decision_count} 个 | 行动项 {action_count} 个

【话题概览】
{topics_summary}

【关键决策】
{decisions_summary}

【行动项】
{actions_summary}

【约束条件】
{constraints_summary}

【核心观点】
{claims_summary}

【分歧与争议】
{disagreements_summary}

【未解决问题】
{open_questions_summary}

请生成一份专业、简洁的日报，格式如下：

# 📊 {channel_name} 日报
> {date} | 消息 {message_count} 条

## 🎯 核心要点
（3-5条最重要的信息，附带来源）

## 📋 决策与行动
（列出决策和待办事项）

## ⚠️ 约束与风险
（列出需要注意的限制条件）

## 💬 观点与讨论
（主要观点，保留不同意见）

## ❓ 待解决
（未回答的问题）

---
*可追溯性: {traceability_pct}% 的信息有证据支撑*"""


# ═══════════════════════════════════════════════════════════════════════════════
# Recall Check
# ═══════════════════════════════════════════════════════════════════════════════

RECALL_CHECK_PROMPT = """检查以下提取结果是否遗漏了重要信息：

【原始消息】
{messages}

【已提取内容摘要】
- 决策: {decision_count} 个
- 行动项: {action_count} 个
- 数据点: {data_count} 个
- 观点: {claim_count} 个
- 约束: {constraint_count} 个

【检查清单】
1. 消息中出现的数字/日期/金额是否都被捕获？
2. 带有"但是/不过/反例/改了/撤回"的转折是否被记录？
3. 带有"必须/不要/限制/预算/期限"的约束是否被提取？
4. 明确的任务分配（"我来做/你负责"）是否被记录？
5. URL链接是否都被捕获？

【输出格式】
```json
{{
  "missing_numbers": ["遗漏的数字及上下文"],
  "missing_transitions": ["遗漏的转折观点"],
  "missing_constraints": ["遗漏的约束"],
  "missing_tasks": ["遗漏的任务分配"],
  "missing_urls": ["遗漏的链接"],
  "recall_score": 0.85,
  "suggestions": ["建议补充的内容"]
}}
```"""
