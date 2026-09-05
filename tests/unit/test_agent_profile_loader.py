from __future__ import annotations

from pathlib import Path

import pytest

from agentx.core.agents.loader import AgentProfileLoader


# 功能：內建 planner 角色配置應能被 AgentProfileLoader 載入
# 設計：直接呼叫 load("planner")，驗證關鍵欄位非空
def test_builtin_planner_found() -> None:
    loader = AgentProfileLoader()
    profile = loader.load("planner")
    assert profile is not None
    assert profile.name == "planner"
    assert profile.system_prompt != ""
    assert "read_file" in profile.allowed_tools or len(profile.allowed_tools) > 0


# 功能：內建三種角色均可載入
# 設計：引數化測試所有內建角色名
@pytest.mark.parametrize("role", ["planner", "executor", "reviewer"])
def test_all_builtin_roles_found(role: str) -> None:
    loader = AgentProfileLoader()
    profile = loader.load(role)
    assert profile is not None, f"builtin role '{role}' not found"
    assert profile.allowed_tools  # 每個內建角色都有 allowed_tools


# 功能：未知角色名應返回 None
# 設計：查詢不存在的角色，斷言返回 None 而非拋異常
def test_unknown_role_returns_none() -> None:
    loader = AgentProfileLoader()
    result = loader.load("nonexistent_role_xyz")
    assert result is None


# 功能：TOML 角色配置檔案應被正確解析
# 設計：寫入臨時 TOML 檔案，透過 _parse 解析並驗證所有欄位
def test_toml_parsed(tmp_path: Path) -> None:
    content = """\
[agent]
description = "測試角色"
system_prompt = "你是測試助手。"
allowed_tools = ["read_file", "bash"]
model = "claude-sonnet-4-6"
"""
    p = tmp_path / "tester.toml"
    p.write_text(content, encoding="utf-8")
    loader = AgentProfileLoader()
    profile = loader._parse(p, "tester")
    assert profile.name == "tester"
    assert profile.description == "測試角色"
    assert profile.system_prompt == "你是測試助手。"
    assert "read_file" in profile.allowed_tools
    assert "bash" in profile.allowed_tools
    assert profile.model == "claude-sonnet-4-6"


# 功能：專案本地角色配置應覆蓋內建同名配置
# 設計：在 .agentx/agents/ 中寫入同名 TOML，monkeypatch cwd，斷言載入到本地版本
def test_project_overrides_builtin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_agents = tmp_path / ".agentx" / "agents"
    local_agents.mkdir(parents=True)
    (local_agents / "planner.toml").write_text(
        '[agent]\ndescription = "local planner"\nsystem_prompt = "local prompt"\n'
        'allowed_tools = ["list_dir"]\nmodel = ""\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    loader = AgentProfileLoader()
    profile = loader.load("planner")
    assert profile is not None
    assert profile.description == "local planner"
    assert "list_dir" in profile.allowed_tools
