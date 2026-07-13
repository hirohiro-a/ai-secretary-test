import requests
from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID


def send_line_message(message: str):
    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ],
    }

    response = requests.post(url, headers=headers, json=data, timeout=30)

    print("LINE送信ステータス:", response.status_code)
    print(response.text)

    response.raise_for_status()
