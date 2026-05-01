#!/usr/bin/env python3
import sqlite3
import json
import uuid
import time

DB_PATH = "/home/tomgame/.cc-switch/cc-switch.db"
KIMI_API_KEY = "sk-kimi-NaXQFjsH1rOyETCMkf44MG18GaBlWTdGbhCqvhXgLQK5iBapU4wrpGORKHzbVX1y"
KIMI_BASE_URL = "http://100.74.26.55:8000/coding"
MODEL_NAME = "kimi-for-coding"

def setup_kimi():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    provider_id = str(uuid.uuid4())
    app_type = "claude"
    provider_name = "Kimi For Coding"
    
    settings_config = {
        "env": {
            "ANTHROPIC_BASE_URL": KIMI_BASE_URL,
            "ANTHROPIC_AUTH_TOKEN": KIMI_API_KEY,
            "API_TIMEOUT_MS": "3000000",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": 1,
            "ANTHROPIC_MODEL": MODEL_NAME,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL_NAME,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL_NAME,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL_NAME,
            "ANTHROPIC_REASONING_MODEL": MODEL_NAME
        },
        "includeCoAuthoredBy": False,
        "permissions": {
            "defaultMode": "bypassPermissions"
        }
    }
    
    meta = {
        "commonConfigEnabled": True,
        "endpointAutoSelect": True,
        "apiFormat": "anthropic",
        "category": "cn_official",
        "icon": "kimi",
        "icon_color": "#6366F1"
    }
    
    cursor.execute("DELETE FROM providers WHERE name = ? AND app_type = ?", (provider_name, app_type))
    cursor.execute("DELETE FROM provider_endpoints WHERE provider_id IN (SELECT id FROM providers WHERE name = ? AND app_type = ?)", (provider_name, app_type))
    
    cursor.execute("""
        INSERT INTO providers (id, app_type, name, settings_config, category, created_at, icon, icon_color, meta, is_current, provider_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'anthropic')
    """, (provider_id, app_type, provider_name, json.dumps(settings_config), "cn_official", 
          int(time.time()), "kimi", "#6366F1", json.dumps(meta)))
    
    cursor.execute("""
        UPDATE providers 
        SET is_current = 0 
        WHERE app_type = ? AND id != ?
    """, (app_type, provider_id))
    
    cursor.execute("""
        INSERT INTO provider_endpoints (provider_id, app_type, url, added_at)
        VALUES (?, ?, ?, ?)
    """, (provider_id, app_type, KIMI_BASE_URL, int(time.time())))
    
    conn.commit()
    conn.close()
    
    print("配置完成！")
    print(f"Provider: {provider_name}")
    print(f"Endpoint: {KIMI_BASE_URL}")

if __name__ == "__main__":
    setup_kimi()
