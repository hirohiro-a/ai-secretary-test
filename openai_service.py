import json
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import OpenAI

from config import OPENAI_API_KEY


openai_client = OpenAI(api_key=OPENAI_API_KEY)

JST = ZoneInfo("Asia/Tokyo")

ANALYSIS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ai_secretary_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["reminder", "question", "clarification", "memo"],
                            },
                            "source_text": {"type": "string"},
                            "reply": {"type": "string"},
                            "task": {
                                "anyOf": [
                                    {"type": "null"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "content": {"type": "string"},
                                            "kind": {
                                                "type": "string",
                                                "enum": ["リマインド", "調査", "価格監視", "メモ"],
                                            },
                                            "status": {
                                                "type": "string",
                                                "enum": ["未着手"],
                                            },
                                            "notify": {
                                                "type": "string",
                                                "enum": ["LINE", "Notion", "メール"],
                                            },
                                            "run_datetime": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ]
                                            },
                                            "analysis": {"type": "string"},
                                        },
                                        "required": [
                                            "title",
                                            "content",
                                            "kind",
                                            "status",
                                            "notify",
                                            "run_datetime",
                                            "analysis",
                                        ],
                                        "additionalProperties": False,
                                    },
                                ]
                            },
                        },
                        "required": ["kind", "source_text", "reply", "task"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    },
}


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
以下のメモを用件ごとに分類し、指定された構造のJSONだけを返してください。

現在日時は {current_datetime} です。
タイムゾーンは Asia/Tokyo です。

ルール:

- メモ内に複数の用件があれば、items内で1件ずつ分ける。
- 各itemのkindは reminder、question、clarification、memo のいずれか。
- source_textには、そのitemの判定対象にした元メモの文章だけを原文のまま入れる。他の用件やメモ全文を混ぜず、要約・言い換えをしない。
- reminder: 日時のある通知依頼。replyは空文字、taskに従来のタスク情報を入れる。
- question: 一般知識で回答できる普通の質問。taskはnull、replyに日本語で簡潔に回答する。
- clarification: 実行や回答に必要な情報が不足している依頼。taskはnull、replyで不足情報を質問する。通知依頼で日時が不足している場合もこれに含む。
- memo: 単なるメモや、従来どおりNotion DBへ残す調査・価格監視などの用件。replyは空文字、taskに情報を入れる。
- questionとclarificationでは、replyを必ず空でない文章にする。
- reminderとmemoでは、taskを必ず設定する。

taskのルール:
- title は短い件名。
- content は内容を自然に要約。
- task.kind は「リマインド」「調査」「価格監視」「メモ」のどれか。
- status は「未着手」。
- notify は「LINE」「Notion」「メール」のどれか。指定がなければ「Notion」。
- run_datetime は日時が分かる場合だけISO形式、それ以外はnull。
- analysis には、どう解釈したかを日本語で短く書く。

外部情報の制限:
- Web検索、天気API、ニュースAPI、価格APIは利用できない。
- 天気などで場所や日付が不足している場合はclarificationにして不足情報を質問する。
- 場所と日付があってもリアルタイム情報が必要な場合はquestionにし、現在は外部検索機能が未実装で確認できないとreplyで伝える。

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
                "content": "あなたは自然文メモを分類し、タスクまたは日本語の返答へ変換する秘書です。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        response_format=ANALYSIS_RESPONSE_FORMAT,
    )

    message = response.choices[0].message
    if getattr(message, "refusal", None):
        raise RuntimeError(f"OpenAIが解析を拒否しました: {message.refusal}")

    cleaned = clean_json_text(message.content)

    return json.loads(cleaned)
