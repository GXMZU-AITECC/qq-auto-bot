"""认领管家脚本的截止时间、提醒、取消与完成关闭逻辑。"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "claim_bot", ROOT / ".github" / "scripts" / "claim_bot.py"
)
claim_bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(claim_bot)


def _issue(labels=("认领任务",), assignees=(), body="", number=7):
    return {
        "number": number,
        "state": "open",
        "labels": [{"name": name} for name in labels],
        "assignees": [{"login": login} for login in assignees],
        "body": body,
    }


def _comment_event(issue, body="/receive", commenter="alice", assoc="MEMBER"):
    return {
        "action": "created",
        "issue": issue,
        "comment": {
            "user": {"login": commenter},
            "body": body,
            "author_association": assoc,
        },
    }


def _set_event(monkeypatch, event):
    monkeypatch.setenv("EVENT", json.dumps(event))


def test_parse_deadline_from_visible_line():
    assert claim_bot.parse_deadline("说明\n截止：2026-11-10\n") == datetime(
        2026, 11, 10, 23, 59, tzinfo=claim_bot.BEIJING
    )
    # 兼容 ASCII 冒号
    assert claim_bot.parse_deadline("截止:2026-11-10") is not None


@pytest.mark.parametrize(
    "body",
    ["", "截止 2026-11-10", "截止：2026-13-01", "正文里提到截止：2026-11-10"],
)
def test_parse_deadline_rejects_invalid(body):
    assert claim_bot.parse_deadline(body) is None


def test_deadline_of_falls_back_to_claim_time(monkeypatch):
    issue = _issue(body="没有截止行")
    monkeypatch.setattr(
        claim_bot, "claim_time", lambda number: "2026-11-01T02:00:00Z"
    )
    assert claim_bot.deadline_of(issue) == datetime(
        2026, 11, 8, 10, 0, tzinfo=claim_bot.BEIJING
    )


def test_receive_reply_shows_issue_deadline(monkeypatch):
    issue = _issue(body="## 任务\n\n截止：2026-11-10\n")
    _set_event(monkeypatch, _comment_event(issue))
    comments = []
    monkeypatch.setattr(claim_bot, "other_claims", lambda *args: [])
    monkeypatch.setattr(claim_bot, "assign", lambda *args: None)
    monkeypatch.setattr(claim_bot, "add_label", lambda *args: None)
    monkeypatch.setattr(claim_bot, "comment", lambda n, text: comments.append(text))

    claim_bot.do_claim()

    assert "2026-11-10 23:59（北京时间）" in comments[0]


def test_receive_reply_marks_fallback_deadline(monkeypatch):
    issue = _issue(body="没有截止行")
    _set_event(monkeypatch, _comment_event(issue))
    comments = []
    monkeypatch.setattr(claim_bot, "other_claims", lambda *args: [])
    monkeypatch.setattr(claim_bot, "assign", lambda *args: None)
    monkeypatch.setattr(claim_bot, "add_label", lambda *args: None)
    monkeypatch.setattr(claim_bot, "comment", lambda n, text: comments.append(text))

    claim_bot.do_claim()

    assert "按认领后 7 天" in comments[0]


def test_cancel_only_by_claimer_in_claimed_state(monkeypatch):
    issue = _issue(labels=("认领任务", "已认领"), assignees=("alice",))
    _set_event(monkeypatch, _comment_event(issue, body="/cancel"))
    calls = []
    monkeypatch.setattr(claim_bot, "unassign", lambda n, who: calls.append(("unassign", who)))
    monkeypatch.setattr(claim_bot, "remove_label", lambda n, name: calls.append(("remove", name)))
    monkeypatch.setattr(claim_bot, "comment", lambda n, text: calls.append(("comment", text)))

    claim_bot.do_claim()

    assert ("unassign", "alice") in calls
    assert ("remove", claim_bot.CLAIMED_LABEL) in calls
    assert any("已取消认领" in item[1] for item in calls if item[0] == "comment")


def test_cancel_rejected_while_pr_in_progress(monkeypatch):
    issue = _issue(labels=("认领任务", "进行中"), assignees=("alice",))
    _set_event(monkeypatch, _comment_event(issue, body="/cancel"))
    calls = []
    monkeypatch.setattr(claim_bot, "unassign", lambda *args: calls.append("unassign"))
    monkeypatch.setattr(claim_bot, "comment", lambda n, text: calls.append(text))

    claim_bot.do_claim()

    assert "unassign" not in calls
    assert "关闭该 PR" in calls[0]


def test_cancel_ignored_for_non_claimer(monkeypatch):
    issue = _issue(labels=("认领任务", "已认领"), assignees=("bob",))
    _set_event(monkeypatch, _comment_event(issue, body="/cancel"))
    calls = []
    monkeypatch.setattr(claim_bot, "unassign", lambda *args: calls.append("unassign"))
    monkeypatch.setattr(claim_bot, "comment", lambda *args: calls.append("comment"))

    claim_bot.do_claim()

    assert calls == []


def _run_sweep(monkeypatch, issue, pr_state, deadline):
    calls = {"comments": [], "added": [], "removed": [], "unassigned": []}
    monkeypatch.setattr(claim_bot, "api", lambda method, path, body=None: [issue])
    monkeypatch.setattr(claim_bot, "claimer_pr", lambda number, who: pr_state)
    monkeypatch.setattr(claim_bot, "deadline_of", lambda item: deadline)
    monkeypatch.setattr(claim_bot, "set_state", lambda *args: None)
    monkeypatch.setattr(
        claim_bot, "comment", lambda n, text: calls["comments"].append(text)
    )
    monkeypatch.setattr(
        claim_bot, "add_label", lambda n, name: calls["added"].append(name)
    )
    monkeypatch.setattr(
        claim_bot, "remove_label", lambda n, name: calls["removed"].append(name)
    )
    monkeypatch.setattr(
        claim_bot, "unassign", lambda n, who: calls["unassigned"].append(who)
    )
    claim_bot.do_sweep()
    return calls


def test_sweep_reminds_even_with_open_pr(monkeypatch):
    issue = _issue(labels=("认领任务", "进行中"), assignees=("alice",))
    calls = _run_sweep(
        monkeypatch, issue, "open", datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert claim_bot.WARNED_LABEL in calls["added"]
    assert len(calls["comments"]) == 1 and "截止" in calls["comments"][0]


def test_sweep_reminds_only_once(monkeypatch):
    issue = _issue(labels=("认领任务", "已认领", "已预警"), assignees=("alice",))
    calls = _run_sweep(
        monkeypatch, issue, None, datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert claim_bot.WARNED_LABEL not in calls["added"]
    assert calls["comments"] == []


def test_sweep_releases_at_deadline_without_pr(monkeypatch):
    issue = _issue(labels=("认领任务", "已认领"), assignees=("alice",))
    calls = _run_sweep(
        monkeypatch, issue, None, datetime.now(timezone.utc) - timedelta(hours=1)
    )
    assert calls["unassigned"] == ["alice"]
    assert claim_bot.CLAIMED_LABEL in calls["removed"]
    assert any("自动释放" in text for text in calls["comments"])


def test_sweep_does_not_release_with_open_pr(monkeypatch):
    issue = _issue(labels=("认领任务", "进行中"), assignees=("alice",))
    calls = _run_sweep(
        monkeypatch, issue, "open", datetime.now(timezone.utc) - timedelta(hours=1)
    )
    assert calls["unassigned"] == []


def test_finish_closes_issue(monkeypatch):
    patched = []
    monkeypatch.setattr(claim_bot, "add_label", lambda *args: None)
    monkeypatch.setattr(claim_bot, "remove_label", lambda *args: None)
    monkeypatch.setattr(
        claim_bot,
        "api",
        lambda method, path, body=None: patched.append((method, path, body)),
    )

    claim_bot.finish(9, [claim_bot.CLAIMED_LABEL, claim_bot.TASK_LABEL])

    assert patched == [
        ("PATCH", "/repos/GXMZU-AITECC/qq-auto-bot/issues/9",
         {"state": "closed", "state_reason": "completed"})
    ]
