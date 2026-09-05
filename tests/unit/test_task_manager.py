from __future__ import annotations

from pathlib import Path

import pytest

from agentx.core.task.manager import TaskManager


# 功能：驗證 create 寫入 JSON 檔案並返回正確的 Task 物件
# 設計：用 tmp_path 隔離檔案系統，斷言檔案存在且欄位值正確
def test_create_writes_file(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    task = mgr.create("do something")
    assert task.id == 1
    assert task.subject == "do something"
    assert task.status == "pending"
    assert (tmp_path / "task_1.json").exists()


# 功能：驗證多次 create 的 ID 遞增
# 設計：連續建立兩個任務，斷言 ID 分別為 1 和 2
def test_create_increments_id(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    t1 = mgr.create("first")
    t2 = mgr.create("second")
    assert t1.id == 1
    assert t2.id == 2


# 功能：驗證 create 傳入不存在的 blocked_by 丟擲 ValueError
# 設計：blocked_by=[99] 引用不存在的任務，預期 ValueError
def test_create_invalid_blocked_by_raises(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        mgr.create("dependent", blocked_by=[99])


# 功能：驗證 get 返回正確的 Task
# 設計：create 後立即 get，斷言 subject 一致
def test_get_returns_task(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("hello")
    task = mgr.get(1)
    assert task.subject == "hello"


# 功能：驗證 get 不存在的 ID 丟擲 ValueError
# 設計：不建立任何任務，直接 get(999)，預期 ValueError
def test_get_nonexistent_raises(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    with pytest.raises(ValueError):
        mgr.get(999)


# 功能：驗證 update 修改 status 並寫回檔案
# 設計：create 後 update status="in_progress"，重新 get 斷言狀態已變更
def test_update_status(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("work")
    mgr.update(1, status="in_progress")
    assert mgr.get(1).status == "in_progress"


# 功能：驗證 update status="completed" 會從其他任務的 blocked_by 中清除該 ID
# 設計：建立任務 1，再建立被 1 阻塞的任務 2，完成任務 1 後斷言任務 2 的 blocked_by 為空
def test_update_completed_clears_dependency(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("step 1")
    mgr.create("step 2", blocked_by=[1])
    mgr.update(1, status="completed")
    assert mgr.get(2).blocked_by == []


# 功能：驗證 update add_blocked_by 正確追加依賴
# 設計：先建立兩個任務，再為任務 2 追加對任務 1 的依賴
def test_update_add_blocked_by(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("a")
    mgr.create("b")
    mgr.update(2, add_blocked_by=[1])
    assert 1 in mgr.get(2).blocked_by


# 功能：驗證 update remove_blocked_by 正確移除依賴
# 設計：建立帶依賴的任務，再移除依賴，斷言 blocked_by 為空
def test_update_remove_blocked_by(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("a")
    mgr.create("b", blocked_by=[1])
    mgr.update(2, remove_blocked_by=[1])
    assert mgr.get(2).blocked_by == []


# 功能：驗證 list_all 返回所有任務，按 ID 升序排列
# 設計：建立三個任務後 list_all，斷言數量為 3 且 ID 順序正確
def test_list_all_ordered(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("x")
    mgr.create("y")
    mgr.create("z")
    tasks = mgr.list_all()
    assert len(tasks) == 3
    assert [t.id for t in tasks] == [1, 2, 3]


# 功能：驗證 format_list 輸出包含狀態標記和任務名
# 設計：建立兩個任務並更新其中一個，檢查 format_list 字串內容
def test_format_list_content(tmp_path: Path) -> None:
    mgr = TaskManager(tmp_path)
    mgr.create("alpha")
    mgr.create("beta")
    mgr.update(1, status="completed")
    result = mgr.format_list()
    assert "[x]" in result
    assert "alpha" in result
    assert "beta" in result


# 功能：驗證 TaskManager 重新例項化時能從現有檔案恢復 next_id
# 設計：第一個 mgr 建立 2 個任務，第二個 mgr 讀取同目錄，新任務 ID 應為 3
def test_manager_resumes_id_from_existing_files(tmp_path: Path) -> None:
    mgr1 = TaskManager(tmp_path)
    mgr1.create("first")
    mgr1.create("second")

    mgr2 = TaskManager(tmp_path)
    task = mgr2.create("third")
    assert task.id == 3
