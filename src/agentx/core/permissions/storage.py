from __future__ import annotations

from pathlib import Path

_DEFAULT_POLICY_PATH = Path("~/.agentx/policy.toml")


# 載入 policy.toml 中 [always] 節，返回 {tool_name: "allow"/"deny"}；檔案不存在時返回空字典
def load_policy_file(path: Path | None = None) -> dict[str, str]:
    p = (path or _DEFAULT_POLICY_PATH).expanduser()
    if not p.exists():
        return {}
    result: dict[str, str] = {}
    in_always = False
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[always]":
            in_always = True
            continue
        if stripped.startswith("["):
            in_always = False
            continue
        if in_always and "=" in stripped and not stripped.startswith("#"):
            k, _, v = stripped.partition("=")
            k = k.strip()
            v = v.strip().strip('"')
            if v in ("allow", "deny"):
                result[k] = v
    return result


# 將 {tool_name: "allow"/"deny"} 寫入 policy.toml，覆蓋 [always] 節
def save_policy_file(always: dict[str, str], path: Path | None = None) -> None:
    p = (path or _DEFAULT_POLICY_PATH).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ~/.agentx/policy.toml",
        "# 由 agentx-core 自動管理，手動編輯生效但格式須正確",
        "",
        "[always]",
    ]
    for tool, decision in sorted(always.items()):
        lines.append(f'{tool} = "{decision}"')
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
