import requests
from datetime import datetime, timedelta, timezone

BASE_URL = "https://hacker-news.firebaseio.com/v0"

def get_json(url: str):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()

def format_time(unix_time: int | None):
    if not unix_time:
        return None
    
    return datetime.fromtimestamp(
        unix_time,
        tz=timezone.utc
    ).isoformat()

def get_hn_neweset_posts(hours: int = 24):
    story_ids_url = f"{BASE_URL}/topstories.json"
    story_ids = get_json(story_ids_url)
    posts = []
    earliest_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    for story_id in story_ids:
        item_url = f"{BASE_URL}/item/{story_id}.json"
        item = get_json(item_url)

        if not item:
            continue

        if item.get("deleted") or item.get("dead"):
            continue

        unix_time = item.get("time")
        if not unix_time:
            continue

        published_at = datetime.fromtimestamp(unix_time, tz=timezone.utc)
        if published_at < earliest_time:
            continue

        post = {
            "id": item.get("id"),
            "type": item.get("type"),
            "title": item.get("title"),
            "url": item.get("url"),
            "author": item.get("by"),
            "score": item.get("score", 0),
            "comment_count": item.get("descendants", 0),
            "published_at": published_at.isoformat(),
            "kids": item.get("kids", []),
            "raw": item,
        }

        posts.append(post)

    return posts

if __name__ == "__main__":
    posts = get_hn_neweset_posts(hours=24)

    for index, post in enumerate(posts, start=1):
        print("=" * 80)
        print(f"{index}. {post['title']}")
        print(f"ID: {post['id']}")
        print(f"Type: {post['type']}")
        print(f"Author: {post['author']}")
        print(f"Score: {post['score']}")
        print(f"Comments: {post['comment_count']}")
        print(f"Published at: {post['published_at']}")
        print(f"URL: {post['url']}")
