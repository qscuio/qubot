"""
LLM Prompts for Trader Influence Analysis

All AI prompts are centralized here for easy tuning.
Used by Modules 4, 5, and 6.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Module 4: Opinion Extraction
# ═══════════════════════════════════════════════════════════════════════════════

OPINION_EXTRACTION_SYSTEM_PROMPT = """你是股票交流群分析专家。你的任务是从成员的发言中提取结构化的交易观点。

核心原则：
1. 【只提取明确观点】只提取有明确方向的观点，模糊的不算
2. 【不编造】无法确定的信息标注为null，不要猜测
3. 【区分事前/事后】只提取事前判断，忽略事后复盘
4. 【可追溯】每个观点必须关联到具体消息

你必须严格按JSON格式输出。"""


OPINION_EXTRACTION_PROMPT = """分析以下成员的交易发言，提取核心交易观点。

【成员】{user_name}
【消息记录】(按时间排序)
{messages}

【输出JSON】
```json
{{
  "views": [
    {{
      "stance": "bullish|bearish|neutral",
      "target": "股票代码或板块(如有)",
      "basis": ["判断理由1", "理由2"],
      "conditions": ["条件1: 如果X则Y"],
      "risk_factors": ["可能失效的情况"],
      "message_indices": [0, 2]
    }}
  ],
  "trading_style": "technical|fundamental|sentiment|mixed",
  "core_bias": "一句话总结该成员的核心倾向"
}}
```

【规则】
- stance必须是 bullish/bearish/neutral 之一
- basis至少1条，否则不算有效观点
- message_indices 是该观点相关的消息序号(从0开始)
- 没有明确观点则返回空views数组"""


# ═══════════════════════════════════════════════════════════════════════════════
# Module 5: Profile Summary
# ═══════════════════════════════════════════════════════════════════════════════

PROFILE_SUMMARY_SYSTEM_PROMPT = """你是交易群成员画像分析专家。基于统计数据和提取的观点，生成简洁的成员画像。"""


PROFILE_SUMMARY_PROMPT = """基于以下成员的交易数据，生成画像摘要。

【成员】{user_name}
【统计指标】
- 总发言数: {total_messages}
- 前瞻性判断: {forward_looking_count} (比例: {forward_ratio:.1%})
- 被他人引用: {citation_count} 次
- 引发他人行动: {behavior_change_count} 次
- 事后复盘: {hindsight_count} 次
- 影响力得分: {influence_score:.1f} (排名第 {rank})

【已提取观点】
{views_summary}

【输出JSON】
```json
{{
  "role_type": "leader|analyst|follower|contrarian|noise",
  "trading_style": "technical|fundamental|sentiment|mixed",
  "core_bias": "一句话描述其核心交易倾向",
  "risk_triggers": ["让该成员变得谨慎的因素"],
  "strength": "该成员的主要优点",
  "weakness": "该成员的主要问题"
}}
```

【角色类型说明】
- leader: 意见领袖，观点常被采纳
- analyst: 有独立分析，理性输出
- follower: 跟随他人，较少原创观点
- contrarian: 逆向思维，常有不同意见
- noise: 情绪化，信息价值低"""


# ═══════════════════════════════════════════════════════════════════════════════
# Module 6: Group Insights
# ═══════════════════════════════════════════════════════════════════════════════

GROUP_INSIGHTS_SYSTEM_PROMPT = """你是交易群体行为分析专家。分析群体层面的观点分布和行为模式。"""


GROUP_INSIGHTS_PROMPT = """分析以下交易群的群体特征。

【频道】{channel_name}
【成员影响力分布】
{influence_distribution}

【观点分布】
- 看多倾向成员: {bullish_count} 人
- 看空倾向成员: {bearish_count} 人
- 中性/混合: {neutral_count} 人

【活跃度分布】
- 总成员发言: {total_members} 人
- Top 3 占比: {top3_ratio:.1%}
- Top 10 占比: {top10_ratio:.1%}

【输出JSON】
```json
{{
  "opinion_anchors": ["最具影响力的成员ID"],
  "emotion_amplifiers": ["容易放大情绪的成员ID"],
  "group_susceptibility": 0.5,
  "echo_chamber_score": 0.5,
  "over_reliance_warning": false,
  "over_reliance_users": [],
  "summary": "一段话总结群体特征和风险"
}}
```

【字段说明】
- group_susceptibility: 0-1, 群体容易被带节奏的程度
- echo_chamber_score: 0=回音室(观点一致), 1=多元(观点分散)
- over_reliance_warning: 如果top3占比>60%则警告"""


# ═══════════════════════════════════════════════════════════════════════════════
# Utility: Format Messages for Prompt
# ═══════════════════════════════════════════════════════════════════════════════

def format_messages_for_prompt(
    messages: list,
    max_messages: int = 50,
    max_chars_per_msg: int = 200,
) -> str:
    """Format messages for LLM prompt with token control."""
    lines = []
    
    for i, msg in enumerate(messages[:max_messages]):
        # Get timestamp
        timestamp = getattr(msg, 'timestamp', None)
        if timestamp:
            time_str = timestamp.strftime('%m-%d %H:%M')
        else:
            time_str = ''
        
        # Get text
        text = getattr(msg, 'text', str(msg))
        if len(text) > max_chars_per_msg:
            text = text[:max_chars_per_msg] + '...'
        
        lines.append(f"[{i}] {time_str}: {text}")
    
    if len(messages) > max_messages:
        lines.append(f"... (共{len(messages)}条，仅显示前{max_messages}条)")
    
    return "\n".join(lines)


def format_views_summary(views: list, max_views: int = 10) -> str:
    """Format extracted views for summary prompt."""
    if not views:
        return "(无已提取观点)"
    
    lines = []
    for v in views[:max_views]:
        stance = getattr(v, 'stance', 'unknown')
        if hasattr(stance, 'value'):
            stance = stance.value
        
        target = getattr(v, 'target', '') or ''
        basis = getattr(v, 'basis', [])
        basis_str = "; ".join(basis[:2]) if basis else ''
        
        lines.append(f"- [{stance}] {target}: {basis_str}")
    
    return "\n".join(lines)
