from __future__ import annotations

from pathlib import Path

import pytest

from agentx.core.skills.loader import Skill, SkillLoader


# 功能：內建 review skill 應能被 SkillLoader 查詢到
# 設計：直接呼叫 resolve("review")，不依賴檔案系統之外的任何狀態
def test_builtin_skill_found() -> None:
    loader = SkillLoader()
    skill = loader.resolve("review")
    assert skill is not None
    assert skill.name == "review"
    assert "審查" in skill.description or "review" in skill.description.lower()
    assert skill.system_prompt_template != ""


# 功能：內建 init / summarize / orchestrate skill 均可找到
# 設計：列舉所有內建 skill 名，斷言均能解析
@pytest.mark.parametrize("name", ["init", "review", "summarize", "orchestrate"])
def test_all_builtin_skills_found(name: str) -> None:
    loader = SkillLoader()
    skill = loader.resolve(name)
    assert skill is not None, f"builtin skill '{name}' not found"


# 功能：不存在的 skill 名應返回 None
# 設計：查詢一個不存在的名稱，斷言 resolve 返回 None 而非拋異常
def test_unknown_skill_returns_none() -> None:
    loader = SkillLoader()
    result = loader.resolve("nonexistent_skill_xyz")
    assert result is None


# 功能：render_prompt 應將 $ARGUMENTS 替換為傳入的引數字串
# 設計：構造含 $ARGUMENTS 的 skill，驗證 render_prompt 結果不含 "$ARGUMENTS" 且含引數值
def test_arguments_substituted() -> None:
    loader = SkillLoader()
    skill = Skill(
        name="test",
        description="test skill",
        system_prompt_template="Review this: $ARGUMENTS\nPlease be thorough.",
        allowed_tools=[],
    )
    rendered = loader.render_prompt(skill, "src/foo.py")
    assert "$ARGUMENTS" not in rendered
    assert "src/foo.py" in rendered


# 功能：frontmatter 中的 allowed_tools 列表應被正確解析
# 設計：構造含 allowed_tools 的 Markdown 檔案，透過 _parse_skill_file 解析並驗證結果
def test_frontmatter_parsed(tmp_path: Path) -> None:
    from agentx.core.skills.loader import _parse_skill_file

    content = """\
---
name: custom
description: 自定義 skill 測試
allowed_tools:
  - read_file
  - bash
---
你是一個測試助手，目標：$ARGUMENTS
"""
    p = tmp_path / "custom.md"
    p.write_text(content, encoding="utf-8")
    skill = _parse_skill_file(p)
    assert skill.name == "custom"
    assert skill.description == "自定義 skill 測試"
    assert "read_file" in skill.allowed_tools
    assert "bash" in skill.allowed_tools
    assert "$ARGUMENTS" in skill.system_prompt_template


# 功能：無 frontmatter 的 Markdown 檔案仍可載入，allowed_tools 為空列表
# 設計：寫入純正文 Markdown，斷言解析成功且 allowed_tools=[]
def test_no_frontmatter(tmp_path: Path) -> None:
    from agentx.core.skills.loader import _parse_skill_file

    content = "你是助手，請幫助使用者完成任務：$ARGUMENTS\n"
    p = tmp_path / "plain.md"
    p.write_text(content, encoding="utf-8")
    skill = _parse_skill_file(p)
    assert skill.name == "plain"
    assert skill.allowed_tools == []
    assert "你是助手" in skill.system_prompt_template


# 功能：專案本地 skill 應覆蓋內建同名 skill
# 設計：在 .agentx/skills/ 中寫入同名檔案，用 monkeypatch 修改 cwd，斷言載入到的是本地版本
def test_project_overrides_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_skills = tmp_path / ".agentx" / "skills"
    local_skills.mkdir(parents=True)
    (local_skills / "review.md").write_text(
        "---\nname: review\ndescription: local override\n---\nlocal system prompt $ARGUMENTS\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    loader = SkillLoader()
    skill = loader.resolve("review")
    assert skill is not None
    assert skill.description == "local override"
    assert "local system prompt" in skill.system_prompt_template
