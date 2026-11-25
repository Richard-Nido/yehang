"""加载与选择科普条目。来源核对不等于临床专业审核。"""
import json
from pathlib import Path

def load_cards():
    return json.loads(Path(__file__).with_name("cards.json").read_text(encoding="utf-8"))

def select_cards(cards, context, allowed_ids):
    return [c for c in cards if c["id"] in allowed_ids
            and c.get("internal_review") == "source_checked_by_codex"
            and context in c.get("tags", [])][:3]
