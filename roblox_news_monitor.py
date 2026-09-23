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

    # 🎨 在這裡設定顏色（十進位色碼）
    # 紅色: 15548997, 黃色: 16776960, 綠色: 5763719, 藍色: 3447003
    embed_color = 3447003  # <- 把這裡改成你要的顏色數字

    embed = {
        "title": f"🚀 [Updates / Announcements] 新公告",
        "description": f"**[{title}]({post_url})**",
        "color": embed_color,
        "fields": [
            {"name": "📂 所屬分類", "value": "`Announcements`", "inline": True},
            {"name": "📌 標籤", "value": f"`{tag_str}`", "inline": True},
            {"name": "🕒 發布時間", "value": formatted_time, "inline": False}
        ],
        "footer": {
            "text": "Roblox DevForum Monitor"
        }
    }

    payload = {
        "username": "Roblox 官方公告通知",
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
    # 直接鎖定 Announcements 專屬分類 JSON 網址 (ID: 36)
    url = "https://devforum.roblox.com/c/updates/announcements/36.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    seen_posts = load_seen_posts()
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Discourse 分類頁面的結構在 topic_list 底下
        topics = data.get("topic_list", {}).get("topics", [])
        print(f"正在檢索 Announcements 最新 {len(topics)} 筆公告...")
        
        new_matched_count = 0
        new_seen_ids = set(seen_posts)
        
        now = datetime.now(timezone.utc)
        time_limit = now - timedelta(days=7) # 放寬到 7 天內，確保最近的重要公告全數捕獲
        
        for topic in topics:
            topic_id = topic.get("id")
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
                
            slug = topic.get("slug", "")
            tags = topic.get("tags", [])
            
            new_matched_count += 1
            new_seen_ids.add(topic_id)
            
            post_url = f"https://devforum.roblox.com/t/{slug}/{topic_id}" if slug and topic_id else "https://devforum.roblox.com"
            
            print(f"🔥 [Announcements] {title}")
            send_to_discord(title, post_url, created_at_str, tags)
                
        save_seen_posts(new_seen_ids)
        print(f"檢索完畢。本次新增推送 {new_matched_count} 筆新公告。")
            
    except requests.exceptions.RequestException as e:
        print(f"[錯誤] 網路請求失敗: {e}")
    except ValueError:
        print("[錯誤] 解析 JSON 格式失敗。")

if __name__ == "__main__":
    fetch_roblox_official_news()