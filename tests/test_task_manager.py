import os
import pytest
from task_manager import setup_task_workspace, get_pending_tasks, move_task, copy_tasks_to_next_step, requeue_stalled_and_failed, cleanup_workspace

def test_setup_task_workspace(tmp_path):
    workspace_root = str(tmp_path)
    chapter_name = "chapter1"
    
    paths = setup_task_workspace(workspace_root, chapter_name)
    
    assert paths["base"] == os.path.join(workspace_root, chapter_name)
    assert os.path.exists(paths["logs"])
    assert os.path.exists(paths["terms"])
    
    for step in ["discovery", "translation", "reading"]:
        assert step in paths["steps"]
        for process_dir in ["pending", "in_progress", "failed", "done"]:
            assert process_dir in paths["steps"][step]
            assert os.path.exists(paths["steps"][step][process_dir])

def test_get_pending_tasks(tmp_path):
    pending_dir = tmp_path / "pending"
    pending_dir.mkdir()
    
    (pending_dir / "task1.txt").write_text("test")
    (pending_dir / "task2.txt").write_text("test")
    
    step_paths = {"pending": str(pending_dir)}
    tasks = get_pending_tasks(step_paths)
    
    assert len(tasks) == 2
    assert any("task1.txt" in t for t in tasks)
    assert any("task2.txt" in t for t in tasks)

def test_move_task(tmp_path):
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()
    
    source_file = source_dir / "task.txt"
    source_file.write_text("test")
    
    dest_path = move_task(str(source_file), str(dest_dir))
    
    assert not os.path.exists(source_file)
    assert os.path.exists(dest_path)
    assert dest_path == str(dest_dir / "task.txt")

def test_move_task_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        move_task(str(tmp_path / "nonexistent.txt"), str(tmp_path))

def test_copy_tasks_to_next_step(tmp_path):
    source_done_dir = tmp_path / "done"
    dest_pending_dir = tmp_path / "pending"
    source_done_dir.mkdir()
    dest_pending_dir.mkdir()
    
    (source_done_dir / "chunk_1.txt").write_text("test1")
    (source_done_dir / "chunk_2.txt").write_text("test2")
    (source_done_dir / "other.txt").write_text("test3") # Should not be copied
    
    copy_tasks_to_next_step(str(source_done_dir), str(dest_pending_dir))
    
    copied_files = os.listdir(dest_pending_dir)
    assert len(copied_files) == 2
    assert "chunk_1.txt" in copied_files
    assert "chunk_2.txt" in copied_files
    assert "other.txt" not in copied_files

def test_requeue_stalled_and_failed(tmp_path):
    step_paths = {
        "discovery": {
            "pending": str(tmp_path / "pending"),
            "in_progress": str(tmp_path / "in_progress"),
            "failed": str(tmp_path / "failed")
        }
    }
    
    for d in step_paths["discovery"].values():
        os.makedirs(d, exist_ok=True)
        
    (tmp_path / "in_progress" / "task1.txt").write_text("test")
    (tmp_path / "failed" / "task2.txt").write_text("test")
    
    requeue_stalled_and_failed(step_paths)
    
    assert len(os.listdir(step_paths["discovery"]["in_progress"])) == 0
    assert len(os.listdir(step_paths["discovery"]["failed"])) == 0
    
    pending_files = os.listdir(step_paths["discovery"]["pending"])
    assert len(pending_files) == 2
    assert "task1.txt" in pending_files
    assert "task2.txt" in pending_files

def test_cleanup_workspace(tmp_path):
    workspace_paths = {"base": str(tmp_path / "workspace")}
    os.makedirs(workspace_paths["base"])
    
    cleanup_workspace(workspace_paths)
    
    assert not os.path.exists(workspace_paths["base"])
