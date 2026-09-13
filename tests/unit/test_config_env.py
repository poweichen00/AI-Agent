from __future__ import annotations

from pathlib import Path

import pytest

from agentx.core.config import get_config


def _write_env(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# 功能：驗證 .env 檔案中的值被正確載入並覆蓋內建預設值
# 設計：寫 .env 到臨時目錄並 chdir 進去，清除同名系統環境變數排除幹擾，確認 .env 載入路徑有效
def test_dotenv_base_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, "AGENTX_PORT=9999\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTX_PORT", raising=False)

    cfg = get_config()

    assert cfg.port == 9999


# 功能：驗證系統環境變數的優先順序高於 .env 檔案中的值
# 設計：.env 寫 9999，系統環境變數寫 8888，確認最終值為 8888，對應四級優先鏈的頂層約束
def test_system_env_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, "AGENTX_PORT=9999\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTX_PORT", "8888")

    cfg = get_config()

    assert cfg.port == 8888


# 功能：驗證 .env 檔案不存在時靜默跳過，使用內建預設值（不拋異常）
# 設計：chdir 到空目錄，清除系統環境變數，確認 get_config() 不因 .env 缺失而崩潰，預設埠為 7437
def test_missing_env_file_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTX_PORT", raising=False)

    cfg = get_config()

    assert cfg.port == 7437


# 功能：驗證 .env 中設定的 AGENTX_CONFIG 能正確影響 TOML 配置檔案的載入路徑
# 設計：.env 指向自定義 TOML 檔案，TOML 中寫入不同埠，確認 .env 在 TOML 載入前被讀取（優先順序鏈的正確順序）
def test_dotenv_before_toml_agentx_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "custom.toml"
    toml_path.write_bytes(b"[core]\nport = 5555\n")

    env_file = tmp_path / ".env"
    _write_env(env_file, f"AGENTX_CONFIG={toml_path}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTX_CONFIG", raising=False)
    monkeypatch.delenv("AGENTX_PORT", raising=False)

    cfg = get_config()

    assert cfg.port == 5555


# 功能：驗證同一變數經過完整四級優先鏈後，最終值為最高優先順序來源（系統環境變數）
# 設計：同時設定預設值(7437)/TOML(6000)/.env(7000)/系統環境變數(8000)，確認最終值為 8000，是優先順序鏈的綜合正確性驗證
def test_priority_chain_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 預設值：7437
    # TOML：6000
    # .env：7000
    # 系統環境變數：8000（最高）
    toml_path = tmp_path / "agentx.toml"
    toml_path.write_bytes(b"[core]\nport = 6000\n")

    env_file = tmp_path / ".env"
    _write_env(env_file, "AGENTX_PORT=7000\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTX_CONFIG", str(toml_path))
    monkeypatch.setenv("AGENTX_PORT", "8000")

    cfg = get_config()

    assert cfg.port == 8000
