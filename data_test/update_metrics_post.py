from newstories import get_json


item_id = 48828943
item = get_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")

score = item.get("score", 0)
comment_count = item.get("descendants", 0)

print(score, comment_count)