"""Analyze news articles — uses LLM when API key is available, falls back to keywords."""

import json
import logging
import os

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一名专业的A股市场财经分析师。你的任务是判断每条新闻是否值得关注，并分析值得关注的新闻。

请分析以下财经新闻，输出JSON格式（纯JSON，不要markdown代码块，不要其他文字）：
{
  "summary": "用3-5句话客观概括新闻核心内容",
  "impact": "positive 或 negative 或 neutral",
  "impact_detail": "简要说明这条新闻对A股市场及相关板块可能的影响（1-2句话）",
  "importance": "major 或 normal",
  "reject": true 或 false
}

判断标准：
- impact 积极/消极：新闻涉及政策利好/利空、行业供需变化、技术突破、重大合作、业绩预增/预亏等
- impact 中性：日常经营动态、无实质影响的常规消息、普通市场波动
- importance major：重大政策出台、行业颠覆性变化、头部公司重大事件、重要经济数据发布
- importance normal：一般性行业动态、常规业务进展
- reject true：这条新闻不重要(importance=normal)且影响中性(impact=neutral)，不值得收录。这类新闻应该被过滤掉。
- reject false：这条新闻值得收录（要么有积极/消极影响，要么是重要事件）"""


def analyze_article(article, api_key="", base_url="", model=""):
    """Analyze a single article. Returns {summary, impact, impact_detail, importance}."""
    if api_key:
        result = _llm_analyze(article, api_key, base_url or "https://api.deepseek.com", model or "deepseek-chat")
        if result:
            return result

    return _fallback_analyze(article)


def _llm_analyze(article, api_key, base_url, model):
    """Use LLM to analyze article content."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        text = (article.get("content") or article.get("snippet") or "")[:3000]
        title = article.get("title", "")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"新闻标题：{title}\n新闻内容：{text}"},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]
        result = json.loads(raw.strip())
        return {
            "summary": result.get("summary", article.get("snippet", "")),
            "impact": result.get("impact", "neutral"),
            "impact_detail": result.get("impact_detail", ""),
            "importance": result.get("importance", "normal"),
            "reject": result.get("reject", False),
        }
    except Exception as e:
        logger.warning("LLM analysis failed: %s", e)
        return None


def _fallback_analyze(article):
    """Simple keyword-based analysis when no LLM available."""
    title = (article.get("title") or "") + " "
    snippet = article.get("snippet") or ""
    text = title + snippet

    positive = ["大涨", "突破", "创新高", "利好", "增长", "政策支持",
                "上涨", "反弹", "提振", "超预期", "加速", "获批", "量产", "放量"]
    negative = ["大跌", "暴跌", "利空", "下跌", "减持", "处罚", "调查",
                "违约", "亏损", "下调", "风险", "退市", "审查"]
    major_kw = ["国务院", "政治局", "央行", "证监会", "重大", "新政",
                "降息", "加息", "万亿", "突发", "制裁", "关税"]

    pos_count = sum(1 for kw in positive if kw in text)
    neg_count = sum(1 for kw in negative if kw in text)

    if pos_count > neg_count:
        impact = "positive"
    elif neg_count > pos_count:
        impact = "negative"
    else:
        impact = "neutral"

    importance = "major" if any(kw in text for kw in major_kw) else "normal"

    return {
        "summary": snippet[:200] if snippet else title[:200],
        "impact": impact,
        "impact_detail": (
            _describe_keywords(text, positive, "积极关键词")
            if pos_count >= neg_count and pos_count > 0
            else _describe_keywords(text, negative, "消极关键词")
            if neg_count > 0
            else "中性消息，无明显倾向"
        ),
        "importance": importance,
        "reject": impact == "neutral" and importance == "normal",
    }


def _describe_keywords(text, keywords, label):
    found = [kw for kw in keywords if kw in text][:3]
    return f"{label}：{'、'.join(found)}"
