import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
USER_ID = os.getenv("LINE_USER_ID")

url = "https://api.line.me/v2/bot/message/push"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

data = {
    "to": USER_ID,
    "messages": [
        {
            "type": "text",
            "text": "こんにちは！AI秘書のLINE通知テスト成功！🎉"
        }
    ]
}

response = requests.post(url, headers=headers, json=data)

print(response.status_code)
print(response.text)