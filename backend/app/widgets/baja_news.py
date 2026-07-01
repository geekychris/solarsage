"""Baja California news — curated RSS feeds.

Same fetch pipeline as ``news.py``; ships with a Baja-focused default
feed list. Inherits from NewsWidget so the auto-translate + caching
logic comes for free — the tab renders through the same ``news`` kind.
"""

from __future__ import annotations

from .news import NewsWidget


class BajaNewsWidget(NewsWidget):
    id = "baja_news"
    kind = "news"          # reuses the news renderer
    name = "Baja news"
    description = (
        "Local Baja California headlines. Defaults to major regional "
        "outlets — swap them via Settings for whichever feeds you follow. "
        "Set ``auto_translate_to: en`` in config to see English "
        "translations inline."
    )
    refresh_seconds = 30 * 60
    default_tab = "Community"
    default_position = 68

    default_config = {
        "feeds": [
            {"label": "Tribuna de San Luis",
             "url": "https://www.tribuna.com.mx/rss/tribuna-de-san-luis"},
            {"label": "Google News · San Felipe BC",
             "url": (
                 "https://news.google.com/rss/search?"
                 "q=%22San+Felipe%22+%22Baja+California%22&hl=es-419&gl=MX&ceid=MX:es"
             )},
            {"label": "Google News · Mexicali",
             "url": (
                 "https://news.google.com/rss/search?"
                 "q=Mexicali&hl=es-419&gl=MX&ceid=MX:es"
             )},
            {"label": "Google News · Baja California",
             "url": (
                 "https://news.google.com/rss/search?"
                 "q=%22Baja+California%22&hl=es-419&gl=MX&ceid=MX:es"
             )},
        ],
        "max_items_per_feed": 5,
        "source_lang": "es",
        "auto_translate_to": "en",
    }
