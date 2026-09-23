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

def get_updates_category_mapping():
    """
    自動追蹤 Updates 主分類 (ID: 45) 以及其底下的所有子分類
    （Announcements, News & Alerts, Release Notes, Community & Events 等）
    """
    url = "https://devforum.roblox.com/categories.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    category_map = {}
    allowed_ids = {45} # 根目錄 Updates ID
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        categories = data.get("category_list", {}).get("categories", [])
        
        cat_info_map = {cat["id"]: cat for cat in categories}
        
        # 遞迴找出所有屬於 updates (ID: 45) 的子分類
        changed = True
        while changed:
            changed = False
            for cat in categories:
                cat_id = cat.get("id")
                parent_id = cat.get("parent_category_id")
                
                if parent_id in allowed_ids and cat_id not in allowed_ids:
                    allowed_ids.add(cat_id)
                    changed = True
                    
                if cat_id in allowed_ids:
                    for sub_id in cat.get("subcategory_ids", []):
                        if sub_id not in allowed_ids:
                            allowed_ids.add(sub_id)
                            changed = True

        # 為每個子分類建立名稱與顏色對應
        for cat_id in allowed_ids:
            if cat_id in cat_info_map:
                cat_name = cat_info_map[cat_id].get("name", "Updates")
            else:
                cat_name = "Updates"
                
            # 根據不同子分類給予不同顏色
            color = 3447003 # 預設藍色
            name_lower = cat_name.lower()
            if "announcement" in name_lower:
                color = 3447003   # 藍色
            elif "news" in name_lower or "alert" in name_lower:
                color = 16761035  # 黃色/金色
            elif "release" in name_lower:
                color = 5763719   # 綠色
            elif "community" in name_lower or "event" in name_lower:
                color = 10181046  # 紫色
                
            category_map[cat_id] = {
                "name": f"Updates / {cat_name}",
                "color": color
            }
            
    except Exception as e:
        print(f"[警告] 無法取得分類對照表: {e}")
        # 預設保底：至少確保 ID 45 能通過
        category_map[45] = {"name": "Updates / Announcements", "color": 3447003}
        
    return category_map

def send_to_discord(title, post_url, created_at, tags, cat_info):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL":
        print("[提示] 尚未設定 Discord Webhook 網址。")
        return

    formatted_time = created_at.replace("T", " ")[:19] if created_at else "未知時間"
    tag_str = ", ".join(tags) if tags else "無"
    
    cat_name = cat_info.get("name", "Updates")
    cat_color = cat_info.get("color", 3447003)

    embed = {
        "title": f"🚀 [{cat_name}] 新動態",
        "description": f"**[{title}]({post_url})**",
        "color": cat_color,
        "fields": [
            {"name": "📂 所屬分類", "value": f"`{cat_name}`", "inline": True},
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
    category_map = get_updates_category_mapping()
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        topics = data.get("topic_list", {}).get("topics", [])
        print(f"正在檢索最新 {len(topics)} 筆討論...")
        
        new_matched_count = 0
        new_seen_ids = set(seen_posts)
        
        now = datetime.now(timezone.utc)
        time_limit = now - timedelta(days=3) # 放寬到 3 天內，確保截圖裡的每週回顧跟路線圖都能被撈出來
        
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
                
            # 檢查是否屬於 Updates 及其四大子分類中
            if category_id not in category_map:
                new_seen_ids.add(topic_id)
                continue
                
            cat_info = category_map[category_id]
            slug = topic.get("slug", "")
            tags = topic.get("tags", [])
            
            new_matched_count += 1
            new_seen_ids.add(topic_id)
            
            post_url = f"https://devforum.roblox.com/t/{slug}/{topic_id}" if slug and topic_id else "https://devforum.roblox.com"
            
            print(f"🔥 [{cat_info['name']}] {title}")
            send_to_discord(title, post_url, created_at_str, tags, cat_info)
                
        save_seen_posts(new_seen_ids)
        print(f"檢索完畢。本次新增推送 {new_matched_count} 筆新討論。")
            
    except requests.exceptions.RequestException as e:
        print(f"[錯誤] 網路請求失敗: {e}")
    except ValueError:
        print("[錯誤] 解析 JSON 格式失敗。")

if __name__ == "__main__":
    fetch_roblox_official_news()