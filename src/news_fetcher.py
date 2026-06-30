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
    list_url_patterns = [
        r"/roll/", r"/list/", r"/news/?(index|list)?$", r"/\d+/$",
        r"stock\.", r"quote", r"realstock",
        r"news\.?roll", r"kuaixun", r"live",
        r"search\?", r"tag/", r"topic/",
    ]
    for pat in list_url_patterns:
        if re.search(pat, url, re.I):
            return True

    # Title/snippet keywords indicating list/aggregation/stock pages
    list_title_kw = [
        "滚动", "快讯", "速递", "行情", "大盘", "早报", "晚报",
        "实时", "涨幅榜", "跌幅榜", "资金流向",
        "今日要闻", "今日热榜", "最新动态", "新闻汇总",
        "涨停", "跌停", "个股", "板块",
    ]
    text = title + snippet
    for kw in list_title_kw:
        if kw in text:
            return True

    # Individual stock mentions (e.g. "XX股份大涨", "XX涨停")
    stock_pattern = re.compile(r'[^\s，。、,]{2,6}(股份|集团|科技|医药|电子|能源|涨停|跌停|大涨|暴跌)')
    matches = stock_pattern.findall(title)
    # If it's a specific stock name followed by action, likely individual stock news
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

        filtered.append(r)

    # Sort: prefer known financial sites
    def _sort_key(r):
        for i, site in enumerate(FINANCE_SITES):
            if site in r["url"]:
                return (0, i)
        return (1, 0)

    filtered.sort(key=_sort_key)
    return filtered[:max_results]


def search_news(direction, max_results=15):
    """Search for recent Chinese financial news about a direction using DuckDuckGo.

    Returns list of dicts: [{title, url, snippet, source}]
    """
    from ddgs import DDGS

    results = []
    queries = [
        f"{direction} 新闻",
        f"{direction} A股 最新",
        f"{direction} 政策 动态",
    ]

    try:
        with DDGS() as ddgs:
            seen = set()
            for query in queries:
                for r in ddgs.text(
                    query,
                    region="cn-zh",
                    timelimit="d",
                    max_results=8,
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
