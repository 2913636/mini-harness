"""组件 6: Recovery 单元测试"""

import pytest
from harness.recovery import Recovery, Checkpoint
from harness.session import Message


def make_msgs(n: int) -> list[Message]:
    return [Message(role="user", content=f"msg{i}") for i in range(n)]


class TestCheckpoint:
    def test_create_checkpoint(self):
        msgs = make_msgs(3)
        cp = Checkpoint(name="before_run", messages_snapshot=msgs, state={"step": 1})
        assert cp.name == "before_run"
        assert len(cp.messages_snapshot) == 3
        assert cp.state["step"] == 1
        assert cp.branch_id == ""


class TestRecovery:
    @pytest.fixture
    def recovery(self):
        return Recovery(max_checkpoints=5)

    def test_save_and_restore_latest(self, recovery):
        msgs = make_msgs(3)
        recovery.save("before_llm", messages=msgs, state={"step": 1})
        cp = recovery.restore()
        assert cp is not None
        assert cp.name == "before_llm"
        assert len(cp.messages_snapshot) == 3
        assert cp.state["step"] == 1

    def test_restore_by_name(self, recovery):
        recovery.save("step1", messages=make_msgs(1), state={"s": 1})
        recovery.save("step2", messages=make_msgs(2), state={"s": 2})
        cp = recovery.restore("step1")
        assert cp is not None
        assert cp.name == "step1"
        assert len(cp.messages_snapshot) == 1

    def test_restore_empty(self, recovery):
        assert recovery.restore() is None

    def test_restore_missing_name(self, recovery):
        recovery.save("s1", messages=make_msgs(1))
        assert recovery.restore("nonexistent") is None

    def test_deep_copy_isolation(self, recovery):
        """Verify snapshot is independent of original"""
        msgs = make_msgs(2)
        recovery.save("before", messages=msgs, state={"key": "value"})
        # Modify original
        msgs[0].content = "MODIFIED"
        # Snapshot should be unchanged
        cp = recovery.restore()
        assert cp is not None
        assert cp.messages_snapshot[0].content == "msg0"

    def test_clear_all(self, recovery):
        recovery.save("s1", messages=make_msgs(1))
        recovery.save("s2", messages=make_msgs(2))
        recovery.clear()
        assert recovery.restore() is None
        assert recovery.checkpoint_count == 0

    def test_clear_by_name(self, recovery):
        recovery.save("s1", messages=make_msgs(1))
        recovery.save("s2", messages=make_msgs(2))
        recovery.clear("s1")
        assert recovery.checkpoint_count == 1
        cp = recovery.restore()
        assert cp is not None
        assert cp.name == "s2"

    def test_latest(self, recovery):
        recovery.save("first", messages=make_msgs(1))
        recovery.save("second", messages=make_msgs(2))
        cp = recovery.latest()
        assert cp is not None
        assert cp.name == "second"

    def test_latest_empty(self, recovery):
        assert recovery.latest() is None

    def test_list_all(self, recovery):
        recovery.save("a", messages=make_msgs(1))
        recovery.save("b", messages=make_msgs(2))
        cps = recovery.list_all()
        assert len(cps) == 2

    def test_max_checkpoints(self, recovery):
        """Old checkpoints should be evicted when max is exceeded"""
        for i in range(10):
            recovery.save(f"cp{i}", messages=make_msgs(1))
        assert recovery.checkpoint_count <= 5
        # Oldest should be gone
        assert recovery.restore("cp0") is None

    def test_recovery_count(self, recovery):
        assert recovery.recovery_count == 0
        recovery.save("s1", messages=make_msgs(1))
        recovery.restore()
        assert recovery.recovery_count == 1
        recovery.restore()
        assert recovery.recovery_count == 2

    # ── 分支级恢复 ──

    def test_save_branch(self, recovery):
        cp = recovery.save_branch("before_b1", branch_id="b1", messages=make_msgs(2), state={"b": 1})
        assert cp.branch_id == "b1"

    def test_restore_branch(self, recovery):
        recovery.save_branch("before_b1", branch_id="b1", messages=make_msgs(2))
        recovery.save_branch("before_b2", branch_id="b2", messages=make_msgs(3))
        cp = recovery.restore_branch("b1")
        assert cp is not None
        assert cp.branch_id == "b1"
        assert len(cp.messages_snapshot) == 2

    def test_restore_branch_by_name(self, recovery):
        recovery.save_branch("step_a", branch_id="b1", messages=make_msgs(1))
        recovery.save_branch("step_b", branch_id="b1", messages=make_msgs(2))
        cp = recovery.restore_branch("b1", "step_a")
        assert cp is not None
        assert cp.name == "step_a"

    def test_restore_branch_missing(self, recovery):
        assert recovery.restore_branch("nonexistent") is None

    def test_clear_branch(self, recovery):
        recovery.save_branch("cp1", branch_id="b1", messages=make_msgs(1))
        recovery.save_branch("cp2", branch_id="b2", messages=make_msgs(2))
        recovery.clear_branch("b1")
        assert recovery.restore_branch("b1") is None
        assert recovery.restore_branch("b2") is not None

    def test_branch_isolation(self, recovery):
        """Branch checkpoints are separate from global checkpoints"""
        recovery.save("global_cp", messages=make_msgs(1))
        recovery.save_branch("b1_cp", branch_id="b1", messages=make_msgs(2))
        # restore() returns the most recent checkpoint (branch one was saved last)
        cp = recovery.restore()
        assert cp is not None
        assert cp.branch_id == "b1"
        # But restore_branch can still find the branch one
        cp_b1 = recovery.restore_branch("b1")
        assert cp_b1 is not None
