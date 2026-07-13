import json
import time

from notion_service import (
    read_memo_text,
    make_hash,
    read_saved_hash,
    save_hash,
    clear_database,
    create_task,
    append_ai_reply,
    get_due_reminders,
    mark_done,
)
from openai_service import parse_with_gpt
from line_service import send_line_message


def update_tasks_if_memo_changed():
    memo_text = read_memo_text()

    if not memo_text:
        print("AI秘書メモが空なので、GPT解析はしません。")
        return False

    current_hash = make_hash(memo_text)
    saved_hash, _ = read_saved_hash()

    if current_hash == saved_hash:
        print("メモ変更なし。GPTは呼びません。")
        return False

    print("メモ変更あり。GPT解析を実行します。")

    result = parse_with_gpt(memo_text)
    items = result.get("items") if isinstance(result, dict) else None

    if not isinstance(items, list) or not items:
        raise ValueError("GPTの解析結果にitems配列がありません。")

    tasks = []
    replies = []
    required_task_keys = {
        "title",
        "content",
        "kind",
        "status",
        "notify",
        "run_datetime",
        "analysis",
    }

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"GPT解析結果の{index}件目がJSONオブジェクトではありません。")

        item_kind = item.get("kind")
        task = item.get("task")
        source_text = item.get("source_text", "").strip()
        reply = item.get("reply", "").strip()

        if item_kind in {"reminder", "memo"}:
            if not isinstance(task, dict):
                raise ValueError(f"GPT解析結果の{index}件目にtaskがありません。")
            missing = required_task_keys - task.keys()
            if missing:
                raise ValueError(
                    f"GPT解析結果の{index}件目のtaskに必須項目がありません: {sorted(missing)}"
                )
            tasks.append(task)
        elif item_kind in {"question", "clarification"}:
            if not source_text:
                raise ValueError(f"GPT解析結果の{index}件目にsource_textがありません。")
            if not reply:
                raise ValueError(f"GPT解析結果の{index}件目にreplyがありません。")
            replies.append(
                {"kind": item_kind, "source_text": source_text, "reply": reply}
            )
        else:
            raise ValueError(f"GPT解析結果の{index}件目の分類が不正です: {item_kind}")

    print("=== GPT解析結果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    database_updated = bool(tasks)
    if database_updated:
        # 質問だけの場合は、既存のリマインダーDBを変更しない。
        clear_database()

        for task in tasks:
            create_task(task)

    append_ai_reply(memo_text, replies, current_hash)

    # DB更新と返答追記がすべて成功してから保存する。
    save_hash(current_hash)

    print(f"{len(tasks)} 件のタスクをAI秘書DBへ登録しました。")
    print(f"{len(replies)} 件の最新返答をAI秘書からの返答ページへ表示しました。")
    print("新しいメモハッシュを保存しました。")

    return database_updated


def notify_due_reminders():
    reminders = get_due_reminders()

    if not reminders:
        print("通知対象のリマインダーはありません。")
        return

    for item in reminders:
        message = f"""🔔 AI秘書リマインド

{item["title"]}

{item["content"]}"""

        send_line_message(message)
        mark_done(item["page_id"])

        print(f"LINE通知して完了にしました: {item['title']}")


def main():
    database_updated = update_tasks_if_memo_changed()

    if database_updated:
        print("Notionの反映を10秒待っています。")
        time.sleep(10)

    notify_due_reminders()


if __name__ == "__main__":
    main()
