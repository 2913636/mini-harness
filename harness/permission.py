"""
组件 2：权限门禁（Permission Gate）

危险操作需用户确认，安全操作自动放行。
→ 对应 Claude Code 的"是否执行这个命令？"弹窗
→ 对应 LangGraph 的 interrupt_before
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Policy(Enum):
    """门禁策略"""
    ALLOW = "allow"        # 自动放行
    DENY = "deny"          # 直接拒绝
    ASK = "ask"            # 需要用户确认


@dataclass
class GateRule:
    """一条门禁规则"""
    tool_name: str          # 适用于哪个工具（"*" 表示所有）
    policy: Policy          # 放行 / 拒绝 / 询问
    reason: str = ""        # 为什么这么设（日志里用）


# 默认安全策略：按工具分类自动判断
DEFAULT_CATEGORY_POLICY = {
    "safe": Policy.ALLOW,      # 计算器、字符串操作 → 自动放行
    "network": Policy.ASK,     # 网络请求 → 询问用户
    "file": Policy.ASK,        # 文件读写 → 询问用户
    "system": Policy.DENY,     # 系统命令 → 默认拒绝
    "general": Policy.ASK,     # 未知分类 → 询问用户
}


class PermissionGate:
    """
    权限门禁 —— 在 Agent 调用工具前做安全检查。

    三层判断优先级（从高到低）：
      1. 精确规则（为特定工具设置）
      2. 通配规则（"*" 规则）
      3. 分类默认策略

    用法：
        gate = PermissionGate()
        gate.add_rule(GateRule("execute_command", Policy.DENY, "禁止执行系统命令"))
        gate.add_rule(GateRule("calculator", Policy.ALLOW, "计算器是安全的"))

        decision = gate.check("calculator")  # → Policy.ALLOW
        decision = gate.check("delete_file") # → Policy.ASK（文件操作需确认）
    """

    def __init__(self, confirm_callback: Optional[Callable] = None):
        """
        Args:
            confirm_callback: 用户确认回调。
                              签名为 (tool_name: str, reason: str) -> bool
                              True = 用户同意，False = 用户拒绝。
                              如果为 None，ASK 策略默认返回 DENY。
        """
        self._rules: dict[str, GateRule] = {}
        self._category_policy = dict(DEFAULT_CATEGORY_POLICY)
        self._confirm_callback = confirm_callback
        self._category_resolver: Optional[Callable] = None

    # ── 规则管理 ────────────────────────

    def add_rule(self, rule: GateRule):
        """添加一条规则（精确匹配优先于通配符）"""
        self._rules[rule.tool_name] = rule

    def remove_rule(self, tool_name: str):
        self._rules.pop(tool_name, None)

    def set_category_resolver(self, resolver: Callable[[str], str]):
        """
        设置分类解析器：给定工具名 → 返回工具分类（safe/network/file/system/general）。
        通常和 ToolRegistry 联动：gate.set_category_resolver(lambda name: registry.get(name).category)
        """
        self._category_resolver = resolver

    def set_confirm_callback(self, callback: Callable):
        """设置用户确认回调"""
        self._confirm_callback = callback

    # ── 核心判断 ────────────────────────

    def check(self, tool_name: str, tool_category: str = "general") -> Policy:
        """
        检查某个工具调用是否被允许。

        优先级：精确规则 > 通配规则("*") > 分类默认策略

        Returns:
            Policy.ALLOW / DENY / ASK
        """
        # 1. 精确规则
        if tool_name in self._rules:
            return self._rules[tool_name].policy

        # 2. 通配规则
        if "*" in self._rules:
            return self._rules["*"].policy

        # 3. 分类默认策略
        category = tool_category
        if self._category_resolver:
            category = self._category_resolver(tool_name)
        return self._category_policy.get(category, Policy.ASK)

    def gate(self, tool_name: str, tool_category: str = "general") -> bool:
        """
        门禁检查的简化接口：返回 True（放行）或 False（拒绝）。

        如果策略是 ASK，调用 confirm_callback 获取用户决定。
        """
        policy = self.check(tool_name, tool_category)

        if policy == Policy.ALLOW:
            return True
        elif policy == Policy.DENY:
            return False
        else:  # ASK
            if self._confirm_callback:
                return self._confirm_callback(tool_name, f"是否允许调用工具 '{tool_name}'？")
            return False  # 无回调时默认拒绝

    # ── 分类策略管理 ────────────────────

    def set_category_policy(self, category: str, policy: Policy):
        """修改某个分类的默认策略"""
        self._category_policy[category] = policy

    def list_rules(self) -> list[GateRule]:
        """列出所有规则（调试用）"""
        return list(self._rules.values())
