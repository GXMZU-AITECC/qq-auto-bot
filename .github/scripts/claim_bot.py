#!/usr/bin/env python3
"""认领管家：管理带「认领任务」标签的 issue 的认领与超时释放。

两个模式：
  claim  —— 由 issue_comment 事件触发：有人回复 /receive 则认领。
  sweep  —— 由定时 / 手动触发：扫描已认领 issue，预警与释放超时。

全程只用 GitHub REST API + 标准库，凭 GITHUB_TOKEN（issues: write）运行。

规则：
  - 只有带「认领任务」标签的 issue 由本脚本管理。
  - 仅组织成员（author_association ∈ MEMBER/OWNER/COLLABORATOR）可认领。
  - 一人同时只能认领一条。
  - 第 5 天还没开 PR → 预警一次；第 7 天还没开 PR → 释放。
  - 有 PR（哪怕没合并）视为进行中，不释放；PR 合并后 issue 自动关闭即完成。
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY", "GXMZU-AITECC/qq-auto-bot")
API = "https://api.github.com"

TASK_LABEL = "认领任务"      # 只有带此标签的 issue 由管家管理
CLAIMED_LABEL = "已认领"
WARNED_LABEL = "已预警"
CMD = "/receive"
LIMIT_DAYS = 7
WARN_DAYS = 5
ALLOWED_ASSOC = {"MEMBER", "OWNER", "COLLABORATOR"}


def api(method: str, path: str, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else None


def _issue_path(number: int) -> str:
    return f"/repos/{REPO}/issues/{number}"


def comment(number: int, text: str) -> None:
    api("POST", f"{_issue_path(number)}/comments", {"body": text})


def event_labels(issue: dict) -> list[str]:
    return [lab["name"] for lab in issue.get("labels", [])]


def add_label(number: int, name: str) -> None:
    api("POST", f"{_issue_path(number)}/labels", {"labels": [name]})


def remove_label(number: int, name: str) -> None:
    try:
        api("DELETE", f"{_issue_path(number)}/labels/{quote(name)}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise


def assign(number: int, login: str) -> None:
    api("POST", f"{_issue_path(number)}/assignees", {"assignees": [login]})


def unassign(number: int, login: str) -> None:
    try:
        api("DELETE", f"{_issue_path(number)}/assignees", {"assignees": [login]})
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise


def timeline(number: int) -> list:
    return api("GET", f"{_issue_path(number)}/timeline?per_page=100") or []


def has_pr(number: int) -> bool:
    """issue 是否被某个 PR 引用过（有 PR = 进行中）。"""
    for ev in timeline(number):
        if ev.get("event") == "cross-referenced":
            src = (ev.get("source") or {}).get("issue") or {}
            if src.get("pull_request"):
                return True
    return False


def claim_time(number: int) -> str | None:
    """最近一次 assigned 事件的时间。"""
    t = None
    for ev in timeline(number):
        if ev.get("event") == "assigned":
            t = ev.get("created_at")
    return t


def days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def other_claims(login: str, exclude: int) -> list[int]:
    """该用户当前认领的其他 issue 编号（一人一条）。"""
    items = api("GET", f"/repos/{REPO}/issues?state=open&assignee={login}&per_page=100") or []
    return [
        i["number"]
        for i in items
        if i["number"] != exclude and CLAIMED_LABEL in [lab["name"] for lab in i.get("labels", [])]
    ]


def do_claim() -> None:
    ev = json.loads(os.environ["EVENT"])
    if ev.get("action") != "created":
        return
    issue = ev["issue"]
    if issue.get("pull_request") or issue.get("state") != "open":
        return

    number = issue["number"]
    if TASK_LABEL not in event_labels(issue):
        return  # 不归管家管的 issue，静默忽略

    body = (ev["comment"].get("body") or "").strip()
    if not body.startswith(CMD):
        return

    commenter = ev["comment"]["user"]["login"]
    assoc = ev["comment"].get("author_association", "")
    assignees = [a["login"] for a in issue.get("assignees", [])]

    if assignees and assignees[0] == commenter:
        comment(number, f"@{commenter} 你已经认领了这条，直接开工即可 👍")
        return
    if assoc not in ALLOWED_ASSOC:
        comment(number, f"@{commenter} 只有团队（组织）成员可以认领本任务。")
        return
    if assignees:
        comment(number, f"这条已被 @{assignees[0]} 认领，请另选一条 🙏")
        return

    others = other_claims(commenter, number)
    if others:
        comment(number, f"@{commenter} 你已认领 #{others[0]}，一人一次一条，完成后再来吧。")
        return

    assign(number, commenter)
    add_label(number, CLAIMED_LABEL)
    comment(
        number,
        f"✅ @{commenter} 认领成功！\n\n"
        f"- 从 `sandbox` 新建分支开发，向 `sandbox` 提 PR，PR 里写 `Closes #{number}`\n"
        f"- 第 {WARN_DAYS} 天若还没开 PR 会提醒一次；第 {LIMIT_DAYS} 天仍无 PR 则自动释放\n"
        f"- 完成后随 PR 合并自动关闭，再接下一条",
    )


def do_sweep() -> None:
    issues = api("GET", f"/repos/{REPO}/issues?state=open&labels={quote(CLAIMED_LABEL)}&per_page=100") or []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        number = issue["number"]
        ls = event_labels(issue)

        assignees = [a["login"] for a in issue.get("assignees", [])]
        if not assignees:
            remove_label(number, CLAIMED_LABEL)
            remove_label(number, WARNED_LABEL)
            continue

        who = assignees[0]
        if has_pr(number):
            continue  # 已开 PR，进行中

        age = days_since(claim_time(number))
        if age is None:
            continue

        if age >= LIMIT_DAYS:
            unassign(number, who)
            remove_label(number, CLAIMED_LABEL)
            remove_label(number, WARNED_LABEL)
            comment(
                number,
                f"⏰ @{who} 认领已超过 {LIMIT_DAYS} 天且没有 PR，本任务自动释放，欢迎重新认领。",
            )
        elif age >= WARN_DAYS and WARNED_LABEL not in ls:
            add_label(number, WARNED_LABEL)
            comment(
                number,
                f"⚠️ @{who} 认领已 {int(age)} 天，还没看到 PR。第 {LIMIT_DAYS} 天会自动释放，加油！",
            )


def main() -> None:
    if not TOKEN:
        print("缺少 GH_TOKEN / GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)
    mode = sys.argv[1] if len(sys.argv) > 1 else "claim"
    if mode == "claim":
        do_claim()
    elif mode == "sweep":
        do_sweep()
    else:
        print(f"未知模式：{mode}（应为 claim / sweep）", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
