"""Profile-specific history actions and their preview counts."""

from storage import schedule
from beta.service import mode

GROUPS = {
    "health": ("primary_sources", "imports"),
    "schedule": (
        "beta_labels",
        "context_history",
        "events",
        "schedule_blocks",
        "planning_blocks",
    ),
    "plans": ("feedback", "plans"),
    "feedback": ("feedback",),
}


def affected(db, profile, group):
    mode(profile)
    if group not in GROUPS:
        raise ValueError("未知的历史类别。")

    def count(table):
        return db.execute(
            f"SELECT count(*) FROM {table} WHERE profile_id=?", (profile,)
        ).fetchone()[0]

    if group == "health":
        return f"{count('samples')} 条健康记录和 {count('imports')} 批导入历史"
    if group == "schedule":
        return f"{count('schedule_blocks') + count('planning_blocks')} 个时段、{count('events')} 个事件及班次标记"
    if group == "plans":
        n = db.execute(
            "SELECT count(distinct plan_id) FROM plans WHERE profile_id=?", (profile,)
        ).fetchone()[0]
        return f"{n} 项休息计划及其 {count('feedback')} 条反馈"
    return f"{count('feedback')} 条执行反馈"


def clear(db, profile, group, revision):
    with schedule.edit(db, profile, mode(profile), revision):
        affected(db, profile, group)
        for table in GROUPS[group]:
            field = "profile" if table == "beta_labels" else "profile_id"
            db.execute(f"DELETE FROM {table} WHERE {field}=?", (profile,))
        db.execute("DELETE FROM explanation_replays WHERE profile_id=?", (profile,))
