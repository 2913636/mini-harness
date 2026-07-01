"""
组件 6：状态恢复（State Recovery）

Agent 执行到一半断了（网络超时、LLM 挂了），能从断点恢复。
→ 对应 LangGraph Checkpoint 恢复
→ 对应 A2A Task 状态追踪
"""

import copy
import time
from dataclasses import dataclass, field


@dataclass
class Checkpoint:
    """一个检查点 —— 保存某时刻的状态快照"""
    name: str                      # 检查点名称（如 "before_tool_call"）
    messages_snapshot: list         # 消息列表副本
    state: dict                    # 自定义状态数据
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)
    branch_id: str = ""            # v2: 哪个分支的检查点


class Recovery:
    """
    状态恢复 —— 为 Agent 提供「断点续跑」能力。

    工作原理：
      1. 关键步骤前 save() 保存快照
      2. 执行操作
      3. 成功后 clear_checkpoint()
      4. 失败后 restore() 恢复到最后一个检查点

    用法：
        recovery = Recovery()

        recovery.save("before_api_call", messages=msgs, state={"step": 3})
        try:
            result = call_api()
            recovery.clear()
        except Exception:
            snapshot = recovery.restore()  # 回到断点
            # 重试或降级处理
    """

    def __init__(self, max_checkpoints: int = 10):
        self._checkpoints: list[Checkpoint] = []
        self._max_checkpoints = max_checkpoints
        self._recovery_count: int = 0  # 统计恢复次数

    # ── 保存检查点 ──────────────────────

    def save(
        self,
        name: str,
        messages: list,
        state: dict | None = None,
        **metadata,
    ) -> Checkpoint:
        """
        保存当前状态为检查点。

        Args:
            name: 检查点名称（如 "before_llm", "after_tool"）
            messages: 当前消息列表
            state: 自定义状态数据
            **metadata: 额外信息
        """
        cp = Checkpoint(
            name=name,
            messages_snapshot=copy.deepcopy(messages),  # 深拷贝，防止后续修改污染快照
            state=copy.deepcopy(state or {}),
            timestamp=time.time(),
            metadata=metadata,
        )
        self._checkpoints.append(cp)

        # 限制检查点数量，删除旧的
        while len(self._checkpoints) > self._max_checkpoints:
            self._checkpoints.pop(0)

        return cp

    # ── 恢复 ────────────────────────────

    def restore(self, name: str = "") -> Checkpoint | None:
        """
        恢复到最近的检查点。

        Args:
            name: 指定检查点名称（空=最近一个）

        Returns:
            Checkpoint 对象，无可用检查点时返回 None
        """
        if not self._checkpoints:
            return None

        if name:
            for cp in reversed(self._checkpoints):
                if cp.name == name:
                    self._recovery_count += 1
                    return cp
            return None

        # 返回最近的检查点
        self._recovery_count += 1
        return self._checkpoints[-1]

    # ── 管理 ────────────────────────────

    def clear(self, name: str = ""):
        """清除检查点"""
        if name:
            self._checkpoints = [cp for cp in self._checkpoints if cp.name != name]
        else:
            self._checkpoints.clear()

    def clear_old(self, name: str):
        """清除指定名称的检查点（保留其他）"""
        self._checkpoints = [cp for cp in self._checkpoints if cp.name != name]

    def latest(self) -> Checkpoint | None:
        """获取最近的检查点（不删除）"""
        return self._checkpoints[-1] if self._checkpoints else None

    def list_all(self) -> list[Checkpoint]:
        """列出所有检查点"""
        return list(self._checkpoints)

    @property
    def recovery_count(self) -> int:
        return self._recovery_count

    @property
    def checkpoint_count(self) -> int:
        return len(self._checkpoints)

    # ── 分支级恢复（v2 新增）────────────

    def save_branch(
        self,
        name: str,
        branch_id: str,
        messages: list,
        state: dict | None = None,
        **metadata,
    ) -> Checkpoint:
        """保存分支检查点（v2 新增）"""
        cp = Checkpoint(
            name=name,
            messages_snapshot=copy.deepcopy(messages),
            state=copy.deepcopy(state or {}),
            timestamp=time.time(),
            metadata=metadata,
            branch_id=branch_id,
        )
        self._checkpoints.append(cp)
        while len(self._checkpoints) > self._max_checkpoints:
            self._checkpoints.pop(0)
        return cp

    def restore_branch(self, branch_id: str, name: str = "") -> Checkpoint | None:
        """恢复到指定分支最近的检查点（v2 新增）"""
        branch_cps = [cp for cp in self._checkpoints if cp.branch_id == branch_id]
        if not branch_cps:
            return None
        if name:
            for cp in reversed(branch_cps):
                if cp.name == name:
                    self._recovery_count += 1
                    return cp
            return None
        self._recovery_count += 1
        return branch_cps[-1]

    def clear_branch(self, branch_id: str):
        """清除指定分支的所有检查点（v2 新增）"""
        self._checkpoints = [cp for cp in self._checkpoints if cp.branch_id != branch_id]
