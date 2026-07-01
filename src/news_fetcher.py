import logging

logger = logging.getLogger(__name__)

# Known Chinese financial news domains - used for source display
FINANCE_SITES = [
    "cls.cn", "wallstreetcn.com", "36kr.com", "stcn.com",
    "eastmoney.com", "xinhuanet.com", "people.com.cn", "yicai.com",
    "21jingji.com", "caixin.com", "sina.com.cn", "chinanews.com",
    "ce.cn", "jrj.com.cn", "10jqka.com.cn", "163.com",
    "qq.com", "thepaper.cn", "guancha.cn", "china.com.cn",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _is_list_page(title, url, snippet):
    """Detect and filter out list/aggregation pages instead of specific news articles."""
    import re

    # URL patterns that indicate list/roll pages
    # Be conservative: many real articles have URLs ending in digits!
    list_url_patterns = [
        r"/roll/", r"/list/", r"/news/?$", r"/kuaixun/?$", r"/live/?$",
        r"stock\.", r"quote", r"realstock",
        r"search\?", r"tag/", r"topic/",
    ]
    for pat in list_url_patterns:
        if re.search(pat, url, re.I):
            return True

    # Title/snippet keywords indicating list/aggregation pages
    list_title_kw = [
        "滚动", "快讯", "速递", "行情", "大盘", "早报", "晚报",
        "实时", "涨幅榜", "跌幅榜", "资金流向",
        "今日要闻", "今日热榜", "最新动态", "新闻汇总",
    ]
    text = title + snippet
    for kw in list_title_kw:
        if kw in text:
            return True

    return False


def _is_stock_fund_price_news(title, url, snippet):
    """Detect individual stock/fund price news that has no industry-level value."""
    import re

    text = title + snippet

    # Individual stock/fund price movement patterns
    price_patterns = [
        # "XX涨超X%", "XX下跌X%", "XX大跌X%"
        r'[^\s，。、,]{2,6}(?:涨超|跌超|下跌|上涨|大涨|暴跌|涨幅|跌幅)\s*[\d.]+\s*[%％]',
        # "XX涨停/跌停" in title (not just snippet)
        r'[^\s，。、,]{2,4}(?:涨停|跌停)',
        # "XX股价" mentions
        r'[^\s，。、,]{2,6}(?:股价|市值)\s*(?:涨|跌|超|达|报)',
        # Stock/fund code patterns: 6 digits (SH/SZ), or ETF/LOF mentions
        r'(?:收盘价|报收)\s*[\d.]+\s*元',
        # "XX概念股大涨/下跌"
        r'[^\s，。、,]{2,8}(?:概念股|板块)\s*(?:大涨|暴跌|走强|走弱|活跃|回调)',
        # Fund-specific: "XX基金净值", "ETF", "LOF"
        r'[^\s，。、,]{2,6}(?:基金|ETF)\s*(?:净值|份额|规模)',
    ]

    for pat in price_patterns:
        if re.search(pat, text):
            return True

    # Specific stock name + price action (e.g. "寒武纪大涨", "中芯国际下跌")
    # But NOT when combined with industry context words
    stock_action = re.compile(
        r'[^\s，。、,]{2,6}(?:股份|集团|科技|医药|电子|能源|智能|生物|材料)'
        r'.{0,8}(?:大涨|暴跌|涨超|跌超|涨停|跌停|上涨|下跌|反弹|回调)'
    )
    matches = stock_action.findall(text)
    if len(matches) >= 2:
        return True

    return False


def _deduplicate_and_filter(results, max_results=15):
    """Deduplicate, remove list pages, sort by quality."""
    seen_urls = set()
    seen_titles = set()
    filtered = []

    for r in results:
        url = r["url"]
        title = r["title"].strip()
        snippet = r.get("snippet", "")

        # URL de-dup
        url_key = url.split("?")[0].rstrip("/")[:80]
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        # Title de-dup
        title_key = title[:40]
        if title_key in seen_titles or len(title) < 10:
            continue
        seen_titles.add(title_key)

        # Filter out list pages and stock quotes
        if _is_list_page(title, url, snippet):
            continue
        if _is_stock_fund_price_news(title, url, snippet):
            logger.debug("  filtered: stock/fund price news (title=%s)", title[:30])
            continue

        filtered.append(r)

    # Sort: prefer known financial sites
    def _sort_key(r):
        for i, site in enumerate(FINANCE_SITES):
            if site in r["url"]:
                return (0, i)
        return (1, 0)

    filtered.sort(key=_sort_key)
    return filtered[:max_results]


def search_news(direction, max_results=15, edition="noon"):
    """Search for recent Chinese financial news about a direction using DuckDuckGo.

    edition: "noon" = 12:00 edition (24h window), "evening" = 21:00 edition (9h window).
    Returns list of dicts: [{title, url, snippet, source}]
    """
    from ddgs import DDGS

    results = []

    # Build search queries based on direction name and edition
    # Evening edition uses shorter time window queries
    # Handle special cases
    if "/" in direction:
        parts = [p.strip() for p in direction.split("/")]
        queries = [
            f"{parts[0]} {parts[1]} 新闻",
            f"{parts[0]} 最新",
            f"{parts[1]} 最新",
        ]
    elif direction == "AI算力":
        queries = [
            "AI算力 芯片 新闻",
            "AI算力 服务器 需求",
            "算力 基础设施 建设",
        ]
    elif direction == "国产半导体设备":
        queries = [
            "国产半导体设备 突破 新闻",
            "半导体 设备 国产化 替代",
            "光刻机 刻蚀 国产 进展",
        ]
    elif direction == "存储":
        queries = [
            "存储芯片 行业 新闻",
            "内存 闪存 市场 动态",
            "存储 半导体 需求",
        ]
    elif direction == "人形机器人":
        queries = [
            "人形机器人 进展 新闻",
            "人形机器人 产业链",
            "机器人 量产 产业化",
        ]
    elif direction == "商业航天":
        queries = [
            "商业航天 新闻",
            "商业航天 发射 卫星",
            "商业航天 政策 动态",
        ]
    else:
        queries = [
            f"{direction} 行业 新闻",
            f"{direction} 最新 动态",
            f"{direction} 政策 新闻",
        ]

    try:
        with DDGS() as ddgs:
            seen = set()
            for query in queries:
                for r in ddgs.text(
                    query,
                    region="cn-zh",
                    timelimit="d",
                    max_results=10,
                ):
                    url = r.get("href", "") or r.get("link", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    results.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "snippet": r.get("body", "") or r.get("snippet", ""),
                        "source": _extract_source(url),
                    })
    except Exception as e:
        logger.warning("DuckDuckGo search failed for '%s': %s", direction, e)

    return _deduplicate_and_filter(results, max_results)


def fetch_article(url, timeout=10):
    """Fetch and extract readable text content from a URL."""
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove non-content elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        content = "\n".join(lines[:150])
        return content[:4000]
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return ""


def _extract_source(url):
    """Extract human-readable source name from a URL."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    # Map common domains to short names
    name_map = {
        "cls.cn": "财联社",
        "wallstreetcn.com": "华尔街见闻",
        "36kr.com": "36氪",
        "stcn.com": "证券时报",
        "eastmoney.com": "东方财富",
        "xinhuanet.com": "新华社",
        "people.com.cn": "人民网",
        "yicai.com": "第一财经",
        "21jingji.com": "21世纪经济报道",
        "caixin.com": "财新网",
        "ce.cn": "中国经济网",
        "jrj.com.cn": "金融界",
        "10jqka.com.cn": "同花顺",
        "thepaper.cn": "澎湃新闻",
        "guancha.cn": "观察者网",
    }
    return name_map.get(domain, domain.split(".")[0].capitalize())
