# mirrordash-news

An RSS and Atom news feed reader module for [MirrorDash](https://github.com/menturan/mirrordash). It fetches headlines and preambles from configurable XML feeds in parallel and displays them in a responsive, snapped HUD layout.

## Features
- **RSS & Atom Support**: Clean XML parsing that supports standard RSS channels and Atom entry namespaces.
- **HTML/XML Tag Stripping**: Automatically cleans up and strips HTML tags, formatting entities, and extra whitespace from titles and preambles.
- **Parallel Fetching**: Loads all configured news sources simultaneously in background threads for rapid refreshes.
- **Glanceable HUD Design**: Snaps layout alignments (left/right/center) depending on its regional position on the mirror, and wraps text cleanly using CSS line-clamping.

## Configuration

Configure this module in your `config.json` file under `modules`:

```json
"mirrordash-news": {
  "enabled": true,
  "position": "bottom_center",
  "interval": 600,
  "max_items": 4,
  "show_preamble": true,
  "feeds": [
    {
      "name": "BBC News",
      "url": "http://feeds.bbci.co.uk/news/rss.xml"
    },
    {
      "name": "SVT Nyheter",
      "url": "https://www.svt.se/nyheter/rss.xml"
    }
  ]
}
```

### Config Options
| Key | Type | Default | Description |
|---|---|---|---|
| `interval` | `integer` | `600` | Refresh interval in seconds between polls (e.g. 600 seconds = 10 minutes). |
| `max_items` | `integer` | `5` | Maximum number of headlines to display at one time. |
| `show_preamble` | `boolean` | `true` | Show the short summary/preamble below the headline. |
| `feeds` | `array` | `[]` | List of feed sources, each containing `name` and XML `url`. |

## Finding RSS/Atom Feeds

Most news sites provide free RSS feeds:
- **BBC News**: `http://feeds.bbci.co.uk/news/rss.xml`
- **SVT Nyheter**: `https://www.svt.se/nyheter/rss.xml`
- **Reuters**: search for public RSS links on their site.
- **CNN**: `http://rss.cnn.com/rss/edition.rss`

Simply add the URL to the `"feeds"` array.

## License
MIT
