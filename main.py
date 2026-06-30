#!/usr/bin/env python3
"""
每日市场新闻日报 - 主入口

从配置文件中读取关注方向 → 搜索各方向新闻 → 分析摘要 →
发送HTML邮件报告。支持 LLM 分析（需要 API key）或关键词兜底。
"""

import logging
import os
import sys
from datetime import datetime

import yaml

from src.news_fetcher import search_news, fetch_article
from src.analyzer import analyze_article
from src.reporter import generate_html_report, send_email

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIRECTIONS_FILE = os.path.join(BASE_DIR, "config", "directions.yml")

# ---------------------------------------------------------------------------
# Load directions
# ---------------------------------------------------------------------------
def load_directions():
    with open(DIRECTIONS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("directions", [])


# ---------------------------------------------------------------------------
# SMTP config from environment (set via GitHub Secrets)
# ---------------------------------------------------------------------------
def get_smtp_config():
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to_addr = os.environ.get("SMTP_TO_ADDR", user)
    return {
        "host": "smtp.qq.com",
        "port": 465,
        "use_ssl": True,
        "user": user,
        "password": password,
        "to_addr": to_addr,
    }


# ---------------------------------------------------------------------------
# LLM config (optional — from environment)
# ---------------------------------------------------------------------------
def get_llm_config():
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    return api_key, base_url, model


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    logger.info("=== 每日市场新闻日报 开始 ===")

    # 1. Dirs
    directions = load_directions()
    logger.info("关注方向 (%d 个): %s", len(directions), directions)

    if not directions:
        logger.warning("没有配置任何关注方向，退出")
        return

    # 2. SMTP
    smtp = get_smtp_config()
    if not smtp["user"] or not smtp["password"]:
        logger.error("SMTP 未配置 (SMTP_USER / SMTP_PASSWORD)，无法发送邮件")
        sys.exit(1)

    # 3. LLM config
    llm_key, llm_url, llm_model = get_llm_config()
    if llm_key:
        logger.info("已配置 LLM API，将使用 AI 进行分析")
    else:
        logger.info("未配置 LLM API，将使用关键词兜底分析")

    # 4. Process each direction
    direction_groups = []
    total = 0

    for direction in directions:
        logger.info("--- 处理: %s ---", direction)

        # Search
        items = search_news(direction, max_results=15)
        logger.info("  搜索到 %d 条", len(items))

        # Fetch content & analyze
        analyzed = []
        for item in items[:8]:  # Fetch top 8 for content
            try:
                content = fetch_article(item["url"])
                item["content"] = content
            except Exception as e:
                logger.debug("  fetch failed: %s", e)
                item["content"] = ""

            # Analyze
            try:
                analysis = analyze_article(item, api_key=llm_key, base_url=llm_url, model=llm_model)
            except Exception as e:
                logger.warning("  analysis error: %s", e)
                analysis = None

            if analysis:
                item["analysis"] = analysis
            else:
                item["analysis"] = {}

            analyzed.append(item)

        # Sort: major first, then by impact (positive > neutral > negative)
        analyzed.sort(key=lambda x: (
            0 if x.get("analysis", {}).get("importance") == "major" else 1,
            -["positive", "neutral", "negative"].index(x.get("analysis", {}).get("impact", "neutral")),
        ))

        # Cap at 5
        top5 = analyzed[:5]
        direction_groups.append({
            "direction": direction,
            "news": top5,
        })
        total += len(top5)
        logger.info("  保留 %d 条", len(top5))

    # 5. Generate report
    date_str = datetime.now().strftime("%Y-%m-%d")
    html = generate_html_report(direction_groups, date_str)

    # 6. Send
    logger.info("发送邮件至 %s...", smtp["to_addr"])
    ok = send_email(smtp, html, date_str)

    if ok:
        logger.info("=== 完成! 共 %d 条新闻 ===", total)
    else:
        logger.error("=== 邮件发送失败 ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
