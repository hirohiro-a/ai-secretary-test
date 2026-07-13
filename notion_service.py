import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from notion_client import Client

from config import (
    NOTION_DATABASE_ID,
    NOTION_MEMO_PAGE_ID,
    NOTION_REPLY_PAGE_ID,
    NOTION_SETTING_PAGE_ID,
    NOTION_TOKEN,
)


JST = ZoneInfo("Asia/Tokyo")
HASH_PREFIX = "memo_hash:"
REPLY_HASH_PREFIX = "AI_SECRETARY_REPLY_HASH:"

notion = Client(auth=NOTION_TOKEN)
_schema_cache = None


def _require_settings():
    required = {
        "NOTION_TOKEN": NOTION_TOKEN,
        "NOTION_MEMO_PAGE_ID": NOTION_MEMO_PAGE_ID,
        "NOTION_DATABASE_ID": NOTION_DATABASE_ID,
        "NOTION_SETTING_PAGE_ID": NOTION_SETTING_PAGE_ID,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"GitHub Secretsが未設定です: {', '.join(missing)}")


def _plain_text(rich_text):
    return "".join(item.get("plain_text", "") for item in (rich_text or []))


def _rich_text(content):
    return [{"type": "text", "text": {"content": str(content)[:2000]}}]


def _iter_block_children(block_id):
    cursor = None
    while True:
        kwargs = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.blocks.children.list(**kwargs)
        for block in response.get("results", []):
            yield block
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")


def _block_text(block):
    block_type = block.get("type")
    value = block.get(block_type, {})
    if "rich_text" in value:
        return _plain_text(value["rich_text"])
    if block_type == "child_page":
        return value.get("title", "")
    return ""


def _read_page_text(page_id):
    lines = []
    for block in _iter_block_children(page_id):
        text = _block_text(block).strip()
        if text:
            lines.append(text)
        if block.get("has_children"):
            child_text = _read_page_text(block["id"])
            if child_text:
                lines.append(child_text)
    return "\n".join(lines)


def read_memo_text():
    _require_settings()
    return _read_page_text(NOTION_MEMO_PAGE_ID).strip()


def make_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_saved_hash():
    _require_settings()
    for block in _iter_block_children(NOTION_SETTING_PAGE_ID):
        text = _block_text(block).strip()
        if text.startswith(HASH_PREFIX):
            return text[len(HASH_PREFIX):].strip(), block["id"]
    return None, None


def save_hash(value):
    _, block_id = read_saved_hash()
    text = f"{HASH_PREFIX} {value}"
    paragraph = {"rich_text": _rich_text(text)}

    if block_id:
        notion.blocks.update(block_id=block_id, paragraph=paragraph)
    else:
        notion.blocks.children.append(
            block_id=NOTION_SETTING_PAGE_ID,
            children=[{"object": "block", "type": "paragraph", "paragraph": paragraph}],
        )


def _paragraph_blocks(text):
    text = str(text).strip()
    if not text:
        return []

    blocks = []
    for start in range(0, len(text), 1900):
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _rich_text(text[start:start + 1900])},
            }
        )
    return blocks


def _reply_already_written(source_hash):
    marker = f"{REPLY_HASH_PREFIX}{source_hash}"
    return any(marker in _block_text(block) for block in _iter_block_children(NOTION_REPLY_PAGE_ID))


def append_ai_reply(memo_text, replies, source_hash):
    if not replies:
        return False
    if not NOTION_REPLY_PAGE_ID:
        raise RuntimeError("GitHub Secret NOTION_REPLY_PAGE_ID が未設定です。")
    if _reply_already_written(source_hash):
        print("同じメモのAI返答はすでに保存済みです。重複追記をスキップします。")
        return False

    processed_at = datetime.now(JST).isoformat(timespec="seconds")
    classifications = ", ".join(reply["kind"] for reply in replies)
    children = [
        {"object": "block", "type": "divider", "divider": {}},
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": _rich_text(f"AI秘書からの返答 {processed_at}")},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(f"分類: {classifications}")},
        },
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": _rich_text("元のAI秘書メモ")},
        },
    ]
    children.extend(_paragraph_blocks(memo_text))
    children.append(
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": _rich_text("GPTからの返答")},
        }
    )
    for reply in replies:
        children.extend(_paragraph_blocks(f"[{reply['kind']}] {reply['reply']}"))
    children.append(
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(f"{REPLY_HASH_PREFIX}{source_hash}")},
        }
    )

    notion.blocks.children.append(block_id=NOTION_REPLY_PAGE_ID, children=children)
    return True


def _query_pages():
    cursor = None
    while True:
        kwargs = {"data_source_id": NOTION_DATABASE_ID, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.data_sources.query(**kwargs)
        for page in response.get("results", []):
            if page.get("object") == "page":
                yield page
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")


def _schema():
    global _schema_cache
    if _schema_cache is None:
        response = notion.data_sources.retrieve(data_source_id=NOTION_DATABASE_ID)
        _schema_cache = response.get("properties", {})
    return _schema_cache


def _find_property(preferred_names, allowed_types=None):
    schema = _schema()
    for name in preferred_names:
        prop = schema.get(name)
        if prop and (not allowed_types or prop.get("type") in allowed_types):
            return name, prop.get("type")
    if allowed_types:
        matches = [
            (name, prop.get("type"))
            for name, prop in schema.items()
            if prop.get("type") in allowed_types
        ]
        if len(matches) == 1:
            return matches[0]
    return None, None


def _property(page, preferred_names, allowed_types=None):
    properties = page.get("properties", {})
    for name in preferred_names:
        prop = properties.get(name)
        if prop and (not allowed_types or prop.get("type") in allowed_types):
            return prop
    if allowed_types:
        matches = [prop for prop in properties.values() if prop.get("type") in allowed_types]
        if len(matches) == 1:
            return matches[0]
    return None


def _option_name(prop):
    if not prop:
        return None
    value = prop.get(prop.get("type"))
    return value.get("name") if isinstance(value, dict) else None


def get_title(page):
    prop = _property(page, ["タイトル", "名前", "Name", "Title"], {"title"})
    return _plain_text(prop.get("title", [])) if prop else "（無題）"


def get_content(page):
    prop = _property(page, ["内容", "詳細", "Content", "Description"], {"rich_text"})
    return _plain_text(prop.get("rich_text", [])) if prop else ""


def get_status(page):
    prop = _property(page, ["状態", "ステータス", "Status"], {"status", "select"})
    return _option_name(prop)


def get_select(page, name):
    aliases = {
        "通知": ["通知", "通知方法", "Notify"],
        "種類": ["種類", "種別", "Kind", "Type"],
    }
    prop = _property(page, aliases.get(name, [name]), {"select", "status"})
    return _option_name(prop)


def get_date(page):
    prop = _property(page, ["実行日時", "通知日時", "日時", "Run datetime"], {"date"})
    date_value = prop.get("date") if prop else None
    return date_value.get("start") if date_value else None


def clear_database():
    for page in list(_query_pages()):
        notion.pages.update(page_id=page["id"], in_trash=True)


def _set_text_property(properties, names, value, property_type):
    name, actual_type = _find_property(names, {property_type})
    if name:
        properties[name] = {actual_type: _rich_text(value)}


def _set_option_property(properties, names, value):
    name, property_type = _find_property(names, {"select", "status"})
    if name and value:
        properties[name] = {property_type: {"name": value}}


def create_task(task):
    properties = {}
    title_name, _ = _find_property(["タイトル", "名前", "Name", "Title"], {"title"})
    if not title_name:
        raise RuntimeError("Notionデータソースにタイトル型プロパティがありません。")

    properties[title_name] = {"title": _rich_text(task["title"])}
    _set_text_property(properties, ["内容", "詳細", "Content", "Description"], task.get("content", ""), "rich_text")
    _set_text_property(properties, ["解析", "分析", "Analysis"], task.get("analysis", ""), "rich_text")
    _set_option_property(properties, ["種類", "種別", "Kind", "Type"], task.get("kind"))
    _set_option_property(properties, ["状態", "ステータス", "Status"], task.get("status", "未着手"))
    _set_option_property(properties, ["通知", "通知方法", "Notify"], task.get("notify"))

    date_name, _ = _find_property(["実行日時", "通知日時", "日時", "Run datetime"], {"date"})
    if date_name and task.get("run_datetime"):
        properties[date_name] = {"date": {"start": task["run_datetime"]}}

    return notion.pages.create(
        parent={"type": "data_source_id", "data_source_id": NOTION_DATABASE_ID},
        properties=properties,
    )


def mark_done(page_id):
    name, property_type = _find_property(["状態", "ステータス", "Status"], {"status", "select"})
    if not name:
        raise RuntimeError("Notionデータソースに状態プロパティがありません。")
    notion.pages.update(
        page_id=page_id,
        properties={name: {property_type: {"name": "完了"}}},
    )


def get_due_reminders():
    _require_settings()
    now = datetime.now(JST)

    print("=== リマインダー判定開始 ===")
    print(f"現在時刻: {now.isoformat()}")

    pages = list(_query_pages())
    print(f"Notionから取得した件数: {len(pages)} 件")
    due = []

    for page in pages:
        title = get_title(page)
        status = get_status(page)
        notify = get_select(page, "通知")
        kind = get_select(page, "種類")
        start = get_date(page)

        print("--------------------")
        print(f"タイトル: {title}")
        print(f"状態: {status}")
        print(f"通知: {notify}")
        print(f"種類: {kind}")
        print(f"実行日時: {start}")

        if status != "未着手" or notify != "LINE" or kind != "リマインド" or not start:
            print("判定: 対象外")
            continue

        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
        except (TypeError, ValueError) as error:
            print(f"判定: 対象外（日付変換エラー: {error}）")
            continue

        if dt <= now:
            print("判定: LINE通知対象")
            due.append(
                {
                    "page_id": page["id"],
                    "title": title,
                    "content": get_content(page),
                    "run_datetime": start,
                }
            )
        else:
            print("判定: 対象外（まだ通知時刻になっていない）")

    print("--------------------")
    print(f"最終的な通知対象: {len(due)} 件")
    print("=== リマインダー判定終了 ===")
    return due
