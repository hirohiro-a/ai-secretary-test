import json
import time

from notion_service import (
    read_memo_text,
    make_hash,
    read_saved_hash,
    save_hash,
    clear_database,
    create_task,
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

    tasks = parse_with_gpt(memo_text)

    if isinstance(tasks, dict):
        tasks = [tasks]

    if not isinstance(tasks, list) or not tasks:
        raise ValueError("GPTの解析結果が空、またはJSON配列ではありません。")

    required_keys = {"title", "content", "kind", "status", "notify"}
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"GPT解析結果の{index}件目がJSONオブジェクトではありません。")
        missing = required_keys - task.keys()
        if missing:
            raise ValueError(
                f"GPT解析結果の{index}件目に必須項目がありません: {sorted(missing)}"
            )

    print("=== GPT解析結果 ===")
    print(json.dumps(tasks, ensure_ascii=False, indent=2))

    # GPT解析に成功してから、古いDBデータを消す
    clear_database()

    for task in tasks:
        create_task(task)

    save_hash(current_hash)

    print(f"{len(tasks)} 件のタスクをAI秘書DBへ登録しました。")
    print("新しいメモハッシュを保存しました。")

    return True


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
