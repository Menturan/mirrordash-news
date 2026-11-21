import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, ANY
from mirrordash_news.plugin import NewsModule, strip_html, parse_feed_xml

MOCK_RSS_DATA = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0">
<channel>
    <title>Mock News Source</title>
    <description>Latest mock news</description>
    <item>
        <title>Headline 1 &amp; SVT</title>
        <description>&lt;p&gt;Preamble 1 with HTML tags.&lt;/p&gt;</description>
        <pubDate>Sun, 07 Jun 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
        <title>Headline 2</title>
        <description>Preamble 2 without tags</description>
    </item>
</channel>
</rss>
"""

MOCK_ATOM_DATA = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Mock Atom Feed</title>
    <entry>
        <title>Atom Headline 1</title>
        <summary>Atom summary 1</summary>
    </entry>
    <entry>
        <title>Atom Headline 2</title>
        <content type="html">Atom content &lt;b&gt;2&lt;/b&gt;</content>
    </entry>
</feed>
"""

def test_strip_html():
    assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"
    assert strip_html("Headline &amp; Preamble") == "Headline & Preamble"
    assert strip_html("   Spaced   Text   ") == "Spaced Text"
    assert strip_html("") == ""
    assert strip_html(None) == ""

def test_parse_feed_xml_rss():
    items = parse_feed_xml(MOCK_RSS_DATA.encode("utf-8"))
    assert len(items) == 2
    assert items[0]["title"] == "Headline 1 & SVT"
    assert items[0]["preamble"] == "Preamble 1 with HTML tags."
    assert items[1]["title"] == "Headline 2"
    assert items[1]["preamble"] == "Preamble 2 without tags"

def test_parse_feed_xml_atom():
    items = parse_feed_xml(MOCK_ATOM_DATA.encode("utf-8"))
    assert len(items) == 2
    assert items[0]["title"] == "Atom Headline 1"
    assert items[0]["preamble"] == "Atom summary 1"
    assert items[1]["title"] == "Atom Headline 2"
    assert items[1]["preamble"] == "Atom content 2"

@pytest.mark.asyncio
async def test_fetch_all_feeds_mapping():
    config = {
        "feeds": [
            {"name": "Mock Source", "url": "http://localhost/rss.xml"},
            {"name": "Down", "url": "http://localhost/down.xml"},
            {"name": "Broken", "url": "http://localhost/broken.xml"},
        ],
        "max_items": 3
    }
    answers = {"http://localhost/rss.xml": (MOCK_RSS_DATA.encode("utf-8"), None),
               "http://localhost/down.xml": (None, "offline"),
               "http://localhost/broken.xml": (b"<html>", None)}

    module = NewsModule(config)
    module.fetch = AsyncMock(side_effect=lambda url, **kw: answers[url])
    items = await module.fetch_all_feeds(config["feeds"])

    assert len(items) == 2
    assert items[0]["source"] == "Mock Source"
    assert items[0]["title"] == "Headline 1 & SVT"

@pytest.mark.asyncio
async def test_render_missing_feeds():
    config = {
        "feeds": [],
        "builtin_feeds": []
    }
    module = NewsModule(config)
    module.render_template = MagicMock(return_value="<div>No Feeds</div>")
    
    html = await module.render()
            
    assert "No Feeds" in html
    module.render_template.assert_called_with(
        "widget.html",
        error="No feeds configured",
        items=[],
        width=420,
        height=300,
        display_mode="list",
        scroll_speed="auto",
        show_header=True
    )

@pytest.mark.asyncio
async def test_scrolling_and_pixel_dimensions():
    config = {
        "feeds": [
            {"name": "Source 1", "url": "http://localhost/rss.xml"}
        ],
        "max_items": 5,
        "width": 500,
        "height": 400,
        "display_mode": "slide_up",
        "scroll_speed": "slow"
    }
    module = NewsModule(config)
    assert module.width == 500
    assert module.height == 400
    assert module.display_mode == "slide_up"
    assert module.scroll_speed == "slow"

    module.render_template = MagicMock(return_value="<div>Rendered</div>")
    # Mock fetch_all_feeds to return some mock news items
    module.fetch_all_feeds = AsyncMock(return_value=[
        {"title": "Test Title", "preamble": "Test description", "source": "Source 1"}
    ])

    html = await module.render()

    assert html == "<div>Rendered</div>"
    module.render_template.assert_called_with(
        "widget.html",
        items=[{"title": "Test Title", "preamble": "Test description", "source": "Source 1"}],
        show_preamble=True,
        width=500,
        height=400,
        display_mode="slide_up",
        scroll_speed="slow",
        error=None,
        show_header=True
    )

@pytest.mark.asyncio
async def test_builtin_feeds_resolution():
    config = {
        "builtin_feeds": ["sr_ekot", "cnn_edition"],
        "custom_feeds": [
            {"name": "Custom Source", "url": "http://localhost/custom.xml"}
        ],
        "max_items": 5
    }
    module = NewsModule(config)
    
    module.fetch_all_feeds = AsyncMock(return_value=[])
    module.render_template = MagicMock(return_value="<div>Rendered</div>")
    await module.render()
            
    # fetch_all_feeds should be called with resolved list
    # sr_ekot + cnn_edition + Custom Source
    module.fetch_all_feeds.assert_called_once()
    called_feeds = module.fetch_all_feeds.call_args[0][0]
    assert len(called_feeds) == 3
    assert called_feeds[0]["name"] == "SR Ekot"
    assert called_feeds[0]["url"] == "https://api.sr.se/api/rss/program/83"
    assert called_feeds[1]["name"] == "CNN"
    assert called_feeds[1]["url"] == "http://rss.cnn.com/rss/edition.rss"
    assert called_feeds[2]["name"] == "Custom Source"
    assert called_feeds[2]["url"] == "http://localhost/custom.xml"


def test_no_never_ending_animation():
    # A never-ending CSS animation redraws the screen 60 times a second and keeps the Pi warm: the list steps instead
    assert "infinite" not in (Path(__file__).parents[1] / "mirrordash_news/templates/widget.html").read_text()


@pytest.mark.parametrize("config, mode", [
    ({"scroll_overflow": True}, "slide_up"),      # saved before display_mode existed
    ({"scroll_overflow": False}, "list"),
    ({}, "list"),
    ({"display_mode": "fade_page", "scroll_overflow": True}, "fade_page"),  # an explicit mode wins
    ({"display_mode": "bogus", "scroll_overflow": True}, "list"),
])
def test_display_mode_derivation(config, mode):
    assert NewsModule(config).display_mode == mode


async def render_real(config):
    """Renders the real template; the module base class's render_template is stood in for."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(Path(__file__).parents[1] / "mirrordash_news/templates"), autoescape=True)
    module = NewsModule({"builtin_feeds": [], "custom_feeds": [{"name": "S", "url": "http://x"}], **config})
    module.render_template = lambda name, **ctx: env.get_template(name).render(translations={}, **ctx)
    module.fetch_all_feeds = AsyncMock(return_value=[{"title": "T", "preamble": "P", "source": "S"}])
    return await module.render()


@pytest.mark.asyncio
@pytest.mark.parametrize("config, mode", [
    ({"scroll_overflow": True}, "slide_up"),
    ({"display_mode": "fade_one"}, "fade_one"),
    ({"display_mode": "fade_page", "scroll_speed": "fast"}, "fade_page"),
])
async def test_rotating_modes_render_markers(config, mode):
    html = await render_real({"height": 300, **config})
    assert f'data-mode="{mode}"' in html
    assert f'data-speed="{config.get("scroll_speed", "auto")}"' in html
    assert "news-items-rotating" in html


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [
    {"display_mode": "fade_page", "height": 0},
    {"display_mode": "slide_up", "height": 0},
    {"display_mode": "list", "height": 300},
])
async def test_static_list_when_not_rotating(config):
    html = await render_real(config)
    assert "data-mode=" not in html
    assert "root._newsTimer" not in html
    assert 'class="news-items"' in html
