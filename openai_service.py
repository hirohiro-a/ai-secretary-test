import json
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import OpenAI

from config import OPENAI_API_KEY


openai_client = OpenAI(api_key=OPENAI_API_KEY)

JST = ZoneInfo("Asia/Tokyo")


def clean_json_text(text):
    text = text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "", 1)

    if text.startswith("```"):
        text = text.replace("```", "", 1)

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


def parse_with_gpt(memo_text):

    now = datetime.now(JST)
    current_datetime = now.isoformat(timespec="seconds")

    prompt = f"""
あなたは、ひろさん専用のAI秘書です。
以下のメモを読んで、Notionデータベースに登録するためのJSON配列だけを返してください。

現在日時は {current_datetime} です。
タイムゾーンは Asia/Tokyo です。

ルール:

- 出力はJSON配列のみ。説明文は禁止。
- メモ内に複数の用件があれば、1件ずつ分けて配列にする。
- title は短い件名。
- content は内容を自然に要約。
- kind は「リマインド」「調査」「価格監視」「メモ」のどれか。
- status は基本「未着手」。
- notify は「LINE」「Notion」「メール」のどれか。指定がなければ「Notion」。
- run_datetime は日時が分かる場合だけ ISO形式で返す。
- analysis には、どう解釈したかを日本語で短く書く。

- 「1時間前に通知」と書かれている場合は予定時刻の1時間前にする。

- 「今の時間でいいからLINE」「今すぐ通知」「すぐ教えて」と書かれている場合は、現在時刻を直前の00分または30分へ切り下げた時刻を run_datetime としてください。

- このAI秘書は30分に1回（毎時03分・33分頃）実行されます。

- 通知時刻が00分・30分以外の場合は、その時刻以前で最も近い00分または30分に丸めてください。

例
08:30 → 08:30
08:59 → 08:30
09:00 → 09:00
09:01 → 09:00
14:20 → 14:00
14:45 → 14:30

- run_datetime の分は必ず00分または30分にしてください。
- ユーザーが指定した通知時刻より後に設定してはいけません。

- 「9時」「10時」など午前・午後の指定がない場合は午前として扱う。
- 「21時」など13時以上は24時間表記。
- 「夜9時」は21:00。
- 「朝9時」「午前9時」は09:00。
- 「昼12時」は12:00。

メモ:

{memo_text}
"""

    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "あなたは自然文メモをタスク管理用JSON配列に変換する秘書です。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    cleaned = clean_json_text(response.choices[0].message.content)

    return json.loads(cleaned)
