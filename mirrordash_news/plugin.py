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

class NewsModule:
    def __init__(self, config):
        self.config = config
        self.name = "mirrordash_news"
        self.interval = config.get("interval", 600)
        
        self.data_dir = config.get("data_dir")
        self.cache_dir = config.get("cache_dir")
        self.translations = config.get("translations", {})
        self.event_bus = config.get("event_bus")
        
        logger.info(f"Initializing {self.name} module")

    def translate(self, key, default=None):
        return self.translations.get(key, default)

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
        
        # Flatten all lists
        all_items = [item for sublist in results for item in sublist]
        return all_items

    async def run_loop(self, broadcast_func):
        logger.info(f"Starting {self.name} run loop")
        while True:
            try:
                feed_configs = self.config.get("feeds", [])
                max_items = self.config.get("max_items", 5)
                show_preamble = self.config.get("show_preamble", True)
                
                # Check for feeds
                if not feed_configs:
                    html = self.render_template(
                        "widget.html",
                        error=self.translate("no_feeds", "No feeds configured"),
                        items=[]
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
                        error=self.translate("error_fetching", "Error loading news") if len(news_items) == 0 else None,
                        last_checked=datetime.now().strftime("%H:%M")
                    )
                except Exception as fetch_err:
                    logger.error(f"Error fetching news feeds: {fetch_err}")
                    html = self.render_template(
                        "widget.html",
                        items=[],
                        error=self.translate("error_fetching", "Error loading news")
                    )
                
                await broadcast_func(self.name, html)
                
            except asyncio.CancelledError:
                logger.info(f"Stopping {self.name} run loop.")
                raise
            except Exception as e:
                logger.error(f"Error in module {self.name} run_loop: {e}")
                
            await asyncio.sleep(self.interval)
