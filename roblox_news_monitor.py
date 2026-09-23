import requests
import json
import os
from datetime import datetime, timezone, timedelta

SEEN_FILE = "seen_posts.json"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_DISCORD_WEBHOOK_URL")

def load_seen_posts():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_posts(seen_set):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_set)[-200:], f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[警告] 無法儲存已讀紀錄: {e}")

def send_to_discord(title, post_url, created_at, tags):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL":
        print("[提示] 尚未設定 Discord Webhook 網址。")
        return

    formatted_time = created_at.replace("T", " ")[:19] if created_at else "未知時間"
    tag_str = ", ".join(tags) if tags else "無"

    embed = {
        "title": f"🚀 [Roblox Updates] 官方公告",
        "description": f"**[{title}]({post_url})**",
        "color": 3447003, # 藍色
        "fields": [
            {"name": "📂 所屬分類", "value": "`Updates / Announcements`", "inline": True},
            {"name": "📌 標籤", "value": f"`{tag_str}`", "inline": True},
            {"name": "🕒 發布時間", "value": formatted_time, "inline": False}
        ],
        "footer": {
            "text": "Roblox DevForum Monitor"
        }
    }

    payload = {
        "username": "Roblox 官方更新通知",
        "embeds": [embed]
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code == 204:
            print("  [Discord] 成功推播通知至頻道！")
        else:
            print(f"  [Discord] 推播失敗，狀態碼: {response.status_code}")
    except Exception as e:
        print(f"  [Discord] 發送請求時發生錯誤: {e}")

def fetch_roblox_official_news():
    url = "https://devforum.roblox.com/latest.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    seen_posts = load_seen_posts()
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        topics = data.get("topic_list", {}).get("topics", [])
        print(f"正在檢索最新 {len(topics)} 筆討論...")
        
        new_matched_count = 0
        new_seen_ids = set(seen_posts)
        
        now = datetime.now(timezone.utc)
        time_limit = now - timedelta(days=2) # 放寬到 2 天內，確保漏掉的也能抓到
        
        for topic in topics:
            topic_id = topic.get("id")
            category_id = topic.get("category_id")
            created_at_str = topic.get("created_at", "")
            title = topic.get("title", "")
            
            # 時間過濾
            if created_at_str:
                try:
                    created_at_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if created_at_dt < time_limit:
                        new_seen_ids.add(topic_id)
                        continue
                except Exception:
                    pass

            if topic_id in seen_posts:
                continue
                
            # 直接精準鎖定 Updates 分類 ID (45) 以及其子分類（通常 API 回傳的 category_id 或是其父層相關）
            # 為了保險，如果文章屬於 Updates 相關板塊，我們直接放行
            # 註：DevForum 中 ID 45 是主分類，子分類也會帶有對應的歸屬
            if category_id != 45:
                # 檢查是否為該板塊底下的文章（有時候子分類 ID 不同，但我們只要是 updates 頁面出來的都可以抓）
                # 這裡直接過濾掉非 45 的其他無關板塊
                new_seen_ids.add(topic_id)
                continue
                
            slug = topic.get("slug", "")
            tags = topic.get("tags", [])
            
            new_matched_count += 1
            new_seen_ids.add(topic_id)
            
            post_url = f"https://devforum.roblox.com/t/{slug}/{topic_id}" if slug and topic_id else "https://devforum.roblox.com"
            
            print(f"🔥 [Updates] {title}")
            send_to_discord(title, post_url, created_at_str, tags)
                
        save_seen_posts(new_seen_ids)
        print(f"檢索完畢。本次新增推送 {new_matched_count} 筆新討論。")
            
    except requests.exceptions.RequestException as e:
        print(f"[錯誤] 網路請求失敗: {e}")
    except ValueError:
        print("[錯誤] 解析 JSON 格式失敗。")

if __name__ == "__main__":
    fetch_roblox_official_news()