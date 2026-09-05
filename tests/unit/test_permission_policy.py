from __future__ import annotations

from agentx.core.permissions.policy import (
    PermissionDecision,
    ToolPolicy,
    evaluate,
    matches_outside_cwd,
    param_preview,
)

# ── Tier 1: deny_patterns ────────────────────────────────────────────────────

# 功能：驗證 deny_patterns 命中時直接返回 DENY，不繼續檢查後續層
# 設計：配置 deny 模式 "rm\s+-rf"，傳入匹配命令；DENY 在最高優先順序，阻止危險命令
def test_deny_pattern_wins() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        deny_patterns=[r"rm\s+-rf"],
    )
    result = evaluate("bash", {"command": "rm -rf /tmp"}, policy)
    assert result == PermissionDecision.DENY


# 功能：驗證 deny_patterns 不匹配時不影響後續層
# 設計：配置 deny 模式 "rm"，傳入不含 rm 的命令；確認不會誤攔截
def test_deny_pattern_no_match_falls_through() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        deny_patterns=[r"\brm\b"],
        allow_patterns=[r"echo"],
    )
    result = evaluate("bash", {"command": "echo hi"}, policy)
    assert result == PermissionDecision.ALLOW


# ── Tier 2: OUTSIDE_CWD_HEURISTICS ───────────────────────────────────────────

# 功能：驗證絕對路徑命令觸發 OUTSIDE_CWD 強制 ASK，即使 allow_patterns 也包含它
# 設計：核心安全約束——allow_patterns 在第 3 層，OUTSIDE_CWD 在第 2 層，越界命令不可被靜默放行
def test_outside_cwd_absolute_path_forces_ask() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        allow_patterns=[r".*"],  # "allow everything" — should not bypass OUTSIDE_CWD
    )
    result = evaluate("bash", {"command": "cat /etc/hosts"}, policy)
    assert result == PermissionDecision.ASK


# 功能：驗證 ~ 開頭路徑觸發 OUTSIDE_CWD 強制 ASK
# 設計：~ 展開指向 home 目錄，超出 cwd 範圍，必須經使用者確認
def test_outside_cwd_tilde_forces_ask() -> None:
    policy = ToolPolicy(default=PermissionDecision.ASK, allow_patterns=[r".*"])
    result = evaluate("bash", {"command": "ls ~/Documents"}, policy)
    assert result == PermissionDecision.ASK


# 功能：驗證 .. 路徑遍歷觸發 OUTSIDE_CWD 強制 ASK
# 設計：../sibling 越出 cwd，即使 allow_patterns 匹配也必須詢問
def test_outside_cwd_parent_traversal_forces_ask() -> None:
    policy = ToolPolicy(default=PermissionDecision.ASK, allow_patterns=[r".*"])
    result = evaluate("bash", {"command": "ls ../sibling"}, policy)
    assert result == PermissionDecision.ASK


# 功能：驗證 $HOME 變數觸發 OUTSIDE_CWD 強制 ASK
# 設計：$HOME 是絕對路徑的間接引用，與直接寫 /home/user/ 同等風險
def test_outside_cwd_dollar_home_forces_ask() -> None:
    policy = ToolPolicy(default=PermissionDecision.ASK, allow_patterns=[r".*"])
    result = evaluate("bash", {"command": "echo $HOME"}, policy)
    assert result == PermissionDecision.ASK


# 功能：驗證 cd 命令觸發 OUTSIDE_CWD 強制 ASK
# 設計：cd 改變工作目錄，後續相對路徑操作可能越出 cwd，屬於高風險操作
def test_outside_cwd_cd_forces_ask() -> None:
    policy = ToolPolicy(default=PermissionDecision.ASK, allow_patterns=[r".*"])
    result = evaluate("bash", {"command": "cd /tmp && ls"}, policy)
    assert result == PermissionDecision.ASK


# 功能：驗證純相對路徑命令不觸發 OUTSIDE_CWD
# 設計：echo hi / ls src/ 等安全命令應正常走 allow_patterns 或 default 層
def test_relative_path_not_outside_cwd() -> None:
    assert not matches_outside_cwd("echo hello")
    assert not matches_outside_cwd("ls src/")
    assert not matches_outside_cwd("cat README.md")
    assert not matches_outside_cwd("python -m pytest")


# 功能：驗證 deny_patterns 優先於 OUTSIDE_CWD（deny 在 tier 1，先檢查）
# 設計：命令同時命中 deny_patterns 和 outside-cwd，結果應為 DENY 而非 ASK
def test_deny_wins_over_outside_cwd() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        deny_patterns=[r"rm\s+-rf"],
    )
    result = evaluate("bash", {"command": "rm -rf /tmp"}, policy)
    assert result == PermissionDecision.DENY


# ── Tier 3: allow_patterns ───────────────────────────────────────────────────

# 功能：驗證 allow_patterns 命中時返回 ALLOW（在 OUTSIDE_CWD 未命中的前提下）
# 設計：echo 是安全的本地命令，配置 allow_patterns 後不需要使用者審批
def test_allow_pattern_grants_access() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        allow_patterns=[r"^echo\b"],
    )
    result = evaluate("bash", {"command": "echo hello"}, policy)
    assert result == PermissionDecision.ALLOW


# ── Tier 4: tool defaults ─────────────────────────────────────────────────────

# 功能：驗證 bash 工具預設策略是 ASK
# 設計：無任何 patterns 命中時，bash 必須詢問使用者，這是安全底線
def test_bash_default_is_ask() -> None:
    result = evaluate("bash", {"command": "echo hi"})
    assert result == PermissionDecision.ASK


# 功能：驗證 read_file / list_dir / note_save 預設策略是 ALLOW
# 設計：只讀或安全工具預設不打擾使用者，降低許可權疲勞
def test_safe_tools_default_allow() -> None:
    assert evaluate("read_file", {"path": "README.md"}) == PermissionDecision.ALLOW
    assert evaluate("list_dir", {"path": "."}) == PermissionDecision.ALLOW
    assert evaluate("note_save", {"content": "x"}) == PermissionDecision.ALLOW


# 功能：驗證 write_file 預設策略是 ASK
# 設計：寫檔案有副作用，預設需要確認
def test_write_file_default_is_ask() -> None:
    assert evaluate("write_file", {"path": "out.txt", "content": "hi"}) == PermissionDecision.ASK


# 功能：驗證未知工具預設策略是 ASK
# 設計：未在 DEFAULT_POLICIES 中登記的工具應採用最保守策略，防止漏配工具直接執行
def test_unknown_tool_default_is_ask() -> None:
    assert evaluate("some_future_tool", {}) == PermissionDecision.ASK


# ── non-bash tools ─────────────────────────────────────────────────────────────

# 功能：驗證非 bash 工具的 patterns 不參與評估（patterns 僅對 bash 生效）
# 設計：write_file 有 deny_patterns 欄位但工具不是 bash，應走 default (ASK)
def test_patterns_only_apply_to_bash() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        deny_patterns=[r".*"],  # would deny everything if applied
        allow_patterns=[r".*"],
    )
    # write_file is not bash — patterns should be ignored → falls to default
    result = evaluate("write_file", {"path": "x.txt", "content": "hi"}, policy)
    assert result == PermissionDecision.ASK


# ── param_preview ─────────────────────────────────────────────────────────────

# 功能：驗證 param_preview 對已知工具返回 key='value' 格式的摘要
# 設計：TUI 審批卡片依賴這個摘要讓使用者快速理解工具要做什麼，格式必須穩定
def test_param_preview_known_tools() -> None:
    assert param_preview("bash", {"command": "echo hi"}) == "command='echo hi'"
    assert param_preview("read_file", {"path": "README.md"}) == "path='README.md'"
    assert param_preview("note_save", {"content": "Python 3.12"}) == "content='Python 3.12'"


# 功能：驗證 param_preview 超出 60 字元時截斷並加省略號
# 設計：避免審批卡片展示超長命令撐破 UI 佈局
def test_param_preview_truncates_long_value() -> None:
    long_cmd = "echo " + "x" * 100
    preview = param_preview("bash", {"command": long_cmd})
    assert len(preview) <= 75  # key='<60 chars>…' overhead ~11 chars
    assert "…" in preview
