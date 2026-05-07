#!/usr/bin/env python3
"""Test fetching WSB daily discussion threads."""
from social_sentiment import RedditJSONScraper

scraper = RedditJSONScraper()

print("=== Searching WSB daily discussion ===")
dd = scraper.search_subreddit("wallstreetbets", "daily discussion", time_filter="week", limit=5)
for p in dd[:5]:
    title = p['title'][:80]
    print(f"  [{p['id']}] {title} | score={p['score']} | comments={p.get('num_comments',0)}")

print("\n=== Searching WSB daily moves ===")
dm = scraper.search_subreddit("wallstreetbets", "daily moves", time_filter="week", limit=5)
for p in dm[:5]:
    title = p['title'][:80]
    print(f"  [{p['id']}] {title} | score={p['score']} | comments={p.get('num_comments',0)}")

# If we find a daily thread, try fetching its comments
if dd:
    best = max(dd, key=lambda x: x.get('num_comments', 0))
    print(f"\n=== Best daily discussion: {best['title'][:60]} ({best.get('num_comments',0)} comments) ===")
    comments = scraper.get_post_comments("wallstreetbets", best['id'], limit=50)
    print(f"  Fetched {len(comments)} comments")
    for c in comments[:5]:
        body = c.get('body', '')[:100]
        print(f"  - {body}")
