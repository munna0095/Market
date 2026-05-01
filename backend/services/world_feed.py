import feedparser
import time
from typing import List, Dict

class WorldFeedService:
    """
    WorldFeedService — Scrapes free global intelligence feeds.
    Derived from the strategy used by WorldMonitor open-source.
    """
    
    SECTORS = {
        "MILITARY & CONFLICT": [
            "https://www.defenseone.com/rss/all/",
            "https://www.theguardian.com/world/middleeast/rss",
            "https://news.google.com/rss/search?q=(conflict+OR+military+OR+war+OR+hotspot+OR+strike)+when:1d&hl=en-US&gl=US&ceid=US:en"
        ],
        "ENERGY & COMMODITIES": [
            "https://news.google.com/rss/search?q=(OPEC+OR+%22oil+price%22+OR+%22crude+oil%22+OR+WTI+OR+Brent+OR+%22oil+production%22)+when:1d&hl=en-US&gl=US&ceid=US:en",
            "https://oilprice.com/rss/main",
            "https://news.google.com/rss/search?q=(%22natural+gas%22+OR+LNG+OR+uranium+OR+minerals)+when:3d&hl=en-US&gl=US&ceid=US:en"
        ],
        "MACRO-ECONOMY": [
            "https://news.google.com/rss/search?q=(CPI+OR+inflation+OR+GDP+OR+%22economic+data%22+OR+%22jobs+report%22)+when:2d&hl=en-US&gl=US&ceid=US:en",
            "https://www.ft.com/rss/home"
        ],
        "TRADE, SANCTIONS & POLICY": [
            "https://news.google.com/rss/search?q=(%22economic+sanctions%22+OR+%22trade+war%22+OR+tariffs+OR+%22export+ban%22)+when:7d&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=(Fed+OR+ECB+OR+BOJ+OR+%22interest+rates%22+OR+%22monetary+policy%22)+when:2d&hl=en-US&gl=US&ceid=US:en"
        ],
        "NUCLEAR & HOTSPOTS": [
            "https://news.google.com/rss/search?q=(%22nuclear+threat%22+OR+%22nuclear+energy%22+OR+%22atomic+scientists%22+OR+%22iran+attacks%22)+when:7d&hl=en-US&gl=US&ceid=US:en"
        ],
        "WATERWAYS & OUTAGES": [
            "https://news.google.com/rss/search?q=(%22Strait+of+Hormuz%22+OR+%22Suez+Canal%22+OR+%22Panama+Canal%22+OR+%22maritime+security%22)+when:7d&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=(%22internet+outage%22+OR+%22power+grid%22+OR+%22infrastructure+attack%22)+when:3d&hl=en-US&gl=US&ceid=US:en"
        ]
    }

    def __init__(self):
        self.last_fetch_time = 0
        self.cached_news = ""

    def fetch_top_10_events(self) -> str:
        """Fetches 2 top news items from each of the 6 sectors (12 items total)."""
        all_events = []
        
        print("[WorldFeed] Fetching latest global intelligence...")
        
        for sector, urls in self.SECTORS.items():
            sector_events = []
            for url in urls:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:5]: 
                        title = entry.title
                        if title not in [e['title'] for e in all_events]:
                            sector_events.append({
                                "sector": sector,
                                "title": title
                            })
                        if len(sector_events) >= 2:
                            break
                except Exception:
                    continue
                if len(sector_events) >= 2:
                    break
            all_events.extend(sector_events[:2])

        if not all_events:
            return "No recent major geopolitical events found in intelligence feeds."

        # Format into a clean report
        report = "🌍 WORLD MONITOR INTELLIGENCE REPORT (Global Hotspots):\n"
        report += "="*50 + "\n"
        for i, event in enumerate(all_events, 1):
            report += f"{i}. [{event['sector']}] {event['title']}\n"
        report += "="*50
        
        self.cached_news = report
        self.last_fetch_time = time.time()
        return report

# Quick standalone test
if __name__ == "__main__":
    import sys
    # Force UTF-8 encoding for stdout on Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    service = WorldFeedService()
    print(service.fetch_top_10_events())
