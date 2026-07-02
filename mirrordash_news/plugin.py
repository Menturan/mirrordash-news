import asyncio
import logging
import urllib.request
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime

logger = logging.getLogger("mirrordash.modules.mirrordash_news")

def strip_html(text: str) -> str:
    """Helper to unescape HTML entities and strip XML/HTML tags and extra spacing."""
    if not text:
        return ""
    # Unescape HTML entities (e.g., &lt;p&gt; -> <p>)
    text = html.unescape(text)
    # Strip HTML tags
    clean = re.compile('<.*?>')
    cleaned = re.sub(clean, '', text)
    # Collapse multiple spaces and newlines
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def parse_feed_xml(xml_bytes: bytes) -> list[dict]:
    """Parses raw XML bytes into a list of parsed news items, supporting RSS and Atom."""
    try:
        xml_str = xml_bytes.decode("utf-8")
    except Exception:
        xml_str = xml_bytes.decode("latin-1", errors="replace")
        
    root = ET.fromstring(xml_str)
    items = []
    
    # Check if RSS
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            
            title = title_el.text if title_el is not None and title_el.text else ""
            desc = desc_el.text if desc_el is not None and desc_el.text else ""
            
            title = strip_html(title)
            desc = strip_html(desc)
            
            if title:
                items.append({
                    "title": title,
                    "preamble": desc
                })
    else:
        # Check if Atom (uses namespace search)
        entries = root.findall(".//{*}entry")
        for entry in entries:
            title_el = entry.find("{*}title")
            desc_el = entry.find("{*}summary")
            if desc_el is None:
                desc_el = entry.find("{*}content")
                
            title = title_el.text if title_el is not None and title_el.text else ""
            desc = desc_el.text if desc_el is not None and desc_el.text else ""
            
            title = strip_html(title)
            desc = strip_html(desc)
            
            if title:
                items.append({
                    "title": title,
                    "preamble": desc
                })
    return items

def fetch_feed(url: str) -> list[dict]:
    """Synchronous fetch and parse of an RSS/Atom feed URL."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MirrorDash/0.1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                return parse_feed_xml(response.read())
            else:
                logger.error(f"Feed URL {url} returned HTTP status {response.status}")
    except Exception as e:
        logger.error(f"Error fetching feed {url}: {e}")
    return []

BUILTIN_FEED_MAP = {
    "bbc_news": {
        "name": "BBC News",
        "url": "http://feeds.bbci.co.uk/news/rss.xml"
    },
    "cnn_edition": {
        "name": "CNN",
        "url": "http://rss.cnn.com/rss/edition.rss"
    },
    "nyt_homepage": {
        "name": "NYT",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
    },
    "sr_ekot": {
        "name": "SR Ekot",
        "url": "https://api.sr.se/api/rss/program/83"
    },
    "aftonbladet_nyheter": {
        "name": "Aftonbladet",
        "url": "https://rss.aftonbladet.se/rss2/small/pages/sections/nyheter/"
    },
    "expressen_nyheter": {
        "name": "Expressen",
        "url": "https://feeds.expressen.se/nyheter/"
    }
}

class NewsModule:
    def __init__(self, config):
        self.config = config
        self.name = "mirrordash_news"
        self.interval = config.get("interval", 600)
        
        self.data_dir = config.get("data_dir")
        self.cache_dir = config.get("cache_dir")
        self.translations = config.get("translations", {})
        self.event_bus = config.get("event_bus")
        
        # Dimensions and scrolling
        self.width = config.get("width", 420)
        self.height = config.get("height", 300)
        self.scroll_overflow = config.get("scroll_overflow", False)
        self.scroll_speed = config.get("scroll_speed", "medium")
        
        logger.info(f"Initializing {self.name} module")

    def translate(self, key: str, default: str = None) -> str:
        if not hasattr(self, "translations") or not self.translations:
            return default if default is not None else key
        val = self.translations.get(key)
        if val is not None:
            return val
        return default if default is not None else key

    async def fetch_all_feeds(self, feed_configs):
        async def fetch_one(feed_config):
            name = feed_config["name"]
            url = feed_config["url"]
            items = await asyncio.to_thread(fetch_feed, url)
            for item in items:
                item["source"] = name
            return items

        tasks = [fetch_one(cfg) for cfg in feed_configs]
        results = await asyncio.gather(*tasks)
        
        # Interleave lists to ensure a balanced mix of sources in the limited view
        all_items = []
        max_len = max(len(sublist) for sublist in results) if results else 0
        for i in range(max_len):
            for sublist in results:
                if i < len(sublist):
                    all_items.append(sublist[i])
        return all_items

    async def run_loop(self, broadcast_func):
        logger.info(f"Starting {self.name} run loop")
        while True:
            try:
                builtin_keys = self.config.get("builtin_feeds", ["bbc_news"])
                custom_feeds = self.config.get("custom_feeds", self.config.get("feeds", []))
                feed_configs = [BUILTIN_FEED_MAP[key] for key in builtin_keys if key in BUILTIN_FEED_MAP] + custom_feeds
                max_items = self.config.get("max_items", 5)
                show_preamble = self.config.get("show_preamble", True)
                
                # Check for feeds
                if not feed_configs:
                    html = self.render_template(
                        "widget.html",
                        error=self.translate("no_feeds", "No feeds configured"),
                        items=[],
                        width=self.width,
                        height=self.height,
                        scroll_overflow=self.scroll_overflow,
                        scroll_speed=self.scroll_speed
                    )
                    await broadcast_func(self.name, html)
                    await asyncio.sleep(self.interval)
                    continue

                try:
                    news_items = await self.fetch_all_feeds(feed_configs)
                    # Limit items
                    news_items = news_items[:max_items]
                    
                    html = self.render_template(
                        "widget.html",
                        items=news_items,
                        show_preamble=show_preamble,
                        width=self.width,
                        height=self.height,
                        scroll_overflow=self.scroll_overflow,
                        scroll_speed=self.scroll_speed,
                        error=self.translate("error_fetching", "Error loading news") if len(news_items) == 0 else None,
                        last_checked=datetime.now().strftime("%H:%M")
                    )
                except Exception as fetch_err:
                    logger.error(f"Error fetching news feeds: {fetch_err}")
                    html = self.render_template(
                        "widget.html",
                        items=[],
                        error=self.translate("error_fetching", "Error loading news"),
                        width=self.width,
                        height=self.height,
                        scroll_overflow=self.scroll_overflow,
                        scroll_speed=self.scroll_speed
                    )
                
                await broadcast_func(self.name, html)
                
            except asyncio.CancelledError:
                logger.info(f"Stopping {self.name} run loop.")
                raise
            except Exception as e:
                logger.error(f"Error in module {self.name} run_loop: {e}")
                
            await asyncio.sleep(self.interval)
