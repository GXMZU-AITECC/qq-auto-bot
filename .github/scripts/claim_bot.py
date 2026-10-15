#!/usr/bin/env python3
"""认领管家：管理带「认领任务」标签的 issue 的认领、状态流转与超时释放。

三个模式：
  claim  —— 由 issue_comment 事件触发：有人回复 /receive 则认领。
  pr     —— 由 pull_request 事件触发（跑在 sandbox 上）：按 PR 开 / 合并 / 关闭流转状态。
  sweep  —— 由定时 / 手动触发：扫描受管 issue，兜底流转、预警与释放。

全程只用 GitHub REST API + 标准库，凭 GITHUB_TOKEN（issues: write）运行。

规则：
  - 只有带「认领任务」标签的 issue 由本脚本管理。
  - 仅组织成员（author_association ∈ MEMBER/OWNER/COLLABORATOR）可认领。
  - 一人同时只能认领一条。
  - 状态流转：已认领 →（该认领人开了 PR）进行中 →（该 PR 合并）已完成；
    PR 关闭且未合并则退回「已认领」。计时从认领那刻起算，进行中不停表。
  - 第 5 天还没开 PR → 预警一次；第 7 天还没开 PR → 释放。
  - 「已完成」只贴标签、摘掉「认领任务」，不关 issue。
  - 只有「认领回复」「第 5 天预警」「第 7 天释放」三处发评论，其余流转静默改标签。
"""

import json
import os
import re
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
DOING_LABEL = "进行中"
DONE_LABEL = "已完成"
WARNED_LABEL = "已预警"
ACTIVE_LABELS = (CLAIMED_LABEL, DOING_LABEL)   # 占用中，一人一条的判定依据
CMD = "/receive"
BASE_BRANCH = "sandbox"      # PR 事件只认进 sandbox 的
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


def claimer_pr(number: int, login: str) -> str | None:
    """该认领人开的 PR 的最新状态：'merged' / 'open' / None。

    只认 login 自己开的 PR；别人的提及、以及自己已关闭且未合并的 PR 都不算。
    """
    merged = opened = False
    for ev in timeline(number):
        if ev.get("event") != "cross-referenced":
            continue
        src = (ev.get("source") or {}).get("issue") or {}
        pr = src.get("pull_request") or {}
        if not pr or (src.get("user") or {}).get("login") != login:
            continue
        if pr.get("merged_at"):
            merged = True
        elif src.get("state") == "open":
            opened = True
    if merged:
        return "merged"
    if opened:
        return "open"
    return None


def set_state(number: int, want: str | None, labels: list[str]) -> None:
    """把状态标签收敛成只剩 want（None = 全摘）；只动 已认领 / 进行中。"""
    for name in (CLAIMED_LABEL, DOING_LABEL):
        if name != want and name in labels:
            remove_label(number, name)
    if want and want not in labels:
        add_label(number, want)


def finish(number: int, labels: list[str]) -> None:
    """完成：贴「已完成」，摘掉其余标签（含「认领任务」，从此不再可领）。"""
    if DONE_LABEL not in labels:
        add_label(number, DONE_LABEL)
    for name in (CLAIMED_LABEL, DOING_LABEL, WARNED_LABEL, TASK_LABEL):
        if name in labels:
            remove_label(number, name)


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
    """该用户当前占用中的其它 issue 编号（一人一条）。"""
    items = api("GET", f"/repos/{REPO}/issues?state=open&assignee={login}&per_page=100") or []
    return [
        i["number"]
        for i in items
        if i["number"] != exclude
        and any(lab["name"] in ACTIVE_LABELS for lab in i.get("labels", []))
    ]


def referenced_issues(pr: dict) -> list[int]:
    """从 PR 标题 + 描述里挑出 `#N` 形式的关联 issue 编号。"""
    text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    return sorted({int(n) for n in re.findall(r"#(\d+)", text)})


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
        f"- 从 `{BASE_BRANCH}` 新建分支开发，向 `{BASE_BRANCH}` 提 PR，"
        f"PR 描述里写上 `#{number}`（机器人靠它认关联）\n"
        f"- 第 {WARN_DAYS} 天还没开 PR 会提醒一次；第 {LIMIT_DAYS} 天仍无 PR 则自动释放\n"
        f"- PR 合并后机器人会标记「已完成」，你就可以接下一条",
    )


def do_pr() -> None:
    """pull_request 事件：按 PR 的开 / 合并 / 关闭流转认领状态。"""
    ev = json.loads(os.environ["EVENT"])
    pr = ev.get("pull_request") or {}
    if (pr.get("base") or {}).get("ref") != BASE_BRANCH:
        return
    action = ev.get("action")
    if action not in ("opened", "reopened", "closed"):
        return

    author = (pr.get("user") or {}).get("login")
    merged = bool(pr.get("merged"))
    for number in referenced_issues(pr):
        try:
            issue = api("GET", _issue_path(number))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            continue
        if not issue or issue.get("state") != "open":
            continue
        ls = event_labels(issue)
        if TASK_LABEL not in ls:
            continue
        if author not in [a["login"] for a in issue.get("assignees", [])]:
            continue  # 不是认领人开的 PR，忽略
        if action == "closed":
            if merged:
                finish(number, ls)
            else:
                set_state(number, CLAIMED_LABEL, ls)  # 退回「已认领」，继续计时
        else:
            set_state(number, DOING_LABEL, ls)
            if WARNED_LABEL in ls:
                remove_label(number, WARNED_LABEL)


def do_sweep() -> None:
    issues = api("GET", f"/repos/{REPO}/issues?state=open&labels={quote(TASK_LABEL)}&per_page=100") or []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        number = issue["number"]
        ls = event_labels(issue)

        assignees = [a["login"] for a in issue.get("assignees", [])]
        if not assignees:
            set_state(number, None, ls)   # 无主：清掉残留状态标签
            if WARNED_LABEL in ls:
                remove_label(number, WARNED_LABEL)
            continue

        who = assignees[0]
        state = claimer_pr(number, who)
        if state == "merged":
            finish(number, ls)
            continue
        if state == "open":
            set_state(number, DOING_LABEL, ls)
            if WARNED_LABEL in ls:
                remove_label(number, WARNED_LABEL)
            continue

        # 没有该认领人的 PR：回到「已认领」，继续计时
        set_state(number, CLAIMED_LABEL, ls)

        age = days_since(claim_time(number))
        if age is None:
            continue

        if age >= LIMIT_DAYS:
            unassign(number, who)
            remove_label(number, CLAIMED_LABEL)
            remove_label(number, DOING_LABEL)
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
    elif mode == "pr":
        do_pr()
    elif mode == "sweep":
        do_sweep()
    else:
        print(f"未知模式：{mode}（应为 claim / pr / sweep）", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
