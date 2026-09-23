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

def get_category_mapping():
    url = "https://devforum.roblox.com/categories.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    target_categories = {
        "updates": {"name": "Updates", "color": 3447003},
        "bug reports": {"name": "Bug Reports", "color": 15158332},
        "feature requests": {"name": "Feature Requests", "color": 3066993}
    }
    
    category_map = {}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        categories = data.get("category_list", {}).get("categories", [])
        
        cat_info_map = {cat["id"]: cat for cat in categories}
        
        for cat in categories:
            cat_id = cat.get("id")
            cat_name_lower = cat.get("name", "").lower()
            parent_id = cat.get("parent_category_id")
            
            matched_target = None
            if cat_name_lower in target_categories:
                matched_target = target_categories[cat_name_lower]
            elif parent_id in cat_info_map:
                parent_name_lower = cat_info_map[parent_id].get("name", "").lower()
                if parent_name_lower in target_categories:
                    matched_target = target_categories[parent_name_lower]
            
            if matched_target:
                category_map[cat_id] = matched_target
                for sub_id in cat.get("subcategory_ids", []):
                    category_map[sub_id] = matched_target
                    
    except Exception as e:
        print(f"[警告] 無法取得分類對照表: {e}")
        
    return category_map

def send_to_discord(title, post_url, created_at, tags, cat_info):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL":
        print("[提示] 尚未設定 Discord Webhook 網址。")
        return

    formatted_time = created_at.replace("T", " ")[:19] if created_at else "未知時間"
    tag_str = ", ".join(tags) if tags else "無"
    
    cat_name = cat_info.get("name", "Roblox DevForum")
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
        "username": "Roblox 開發者動態",
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
    category_map = get_category_mapping()
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        topics = data.get("topic_list", {}).get("topics", [])
        print(f"正在檢索最新 {len(topics)} 筆討論...")
        
        new_matched_count = 0
        new_seen_ids = set(seen_posts)
        
        now = datetime.now(timezone.utc)
        time_limit = now - timedelta(days=1)
        
        for topic in topics:
            topic_id = topic.get("id")
            category_id = topic.get("category_id")
            created_at_str = topic.get("created_at", "")
            title = topic.get("title", "")
            
            # 時間過濾 (1天內)
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
                
            # 分類過濾與除錯
            if category_id not in category_map:
                print(f"[略過-分類不符] ID: {category_id} | 標題: {title}")
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