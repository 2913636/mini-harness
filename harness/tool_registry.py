"""
组件 1：工具注册表（Tool Registry）

Agent 能调什么工具，工具的 Schema 是什么，都在注册表里。
→ 对应 MCP Server 的 Tool 列表
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Tool:
    """一个工具的定义，和 MCP Tool Schema 对齐"""
    name: str
    description: str
    parameters: dict  # JSON Schema 格式的参数定义
    fn: Callable  # 实际执行的函数
    category: str = "general"  # 工具分类：safe / network / file / system
    tags: list = field(default_factory=list)

    def to_schema(self) -> dict:
        """导出为 MCP 兼容的工具描述"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters.keys()),
            },
        }


class ToolRegistry:
    """
    工具注册表 —— 统一管理所有 Agent 可调用的工具。

    职责：
      - 注册/注销工具
      - 按名称查找工具
      - 列出所有可用工具（给 LLM 拼 prompt 用）
      - 按分类筛选工具

    用法：
        registry = ToolRegistry()
        registry.register(
            name="calculator",
            description="执行数学计算，参数：expression(算式字符串)",
            parameters={"expression": {"type": "string", "description": "数学表达式"}},
            fn=lambda expression: str(eval(expression)),
            category="safe",
        )
        tool = registry.get("calculator")
        result = tool.fn(expression="2+3")
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    # ── 注册 / 注销 ─────────────────────

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        fn: Callable,
        category: str = "general",
        tags: list | None = None,
    ) -> Tool:
        """注册一个工具。同名工具会覆盖旧注册。"""
        tool = Tool(
            name=name,
            description=description,
            parameters=parameters,
            fn=fn,
            category=category,
            tags=tags or [],
        )
        self._tools[name] = tool
        return tool

    def unregister(self, name: str) -> bool:
        """注销工具，返回是否成功"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    # ── 查询 ────────────────────────────

    def get(self, name: str) -> Optional[Tool]:
        """按名称查找工具"""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """列出所有已注册工具"""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[Tool]:
        """按分类列出工具（safe / network / file / system 等）"""
        return [t for t in self._tools.values() if t.category == category]

    # ── 给 LLM 用的工具描述 ──────────────

    def describe_all(self) -> str:
        """生成所有工具的文本描述，拼到 System Prompt 里"""
        if not self._tools:
            return "（无可用工具）"
        lines = []
        for t in self._tools.values():
            params_desc = ", ".join(
                f"{k}({v.get('type', 'string')})" for k, v in t.parameters.items()
            )
            lines.append(f"- {t.name}: {t.description} | 参数: {params_desc}")
        return "\n".join(lines)

    def describe_for_llm(self) -> list[dict]:
        """导出为 OpenAI function-calling 格式的工具列表"""
        return [t.to_schema() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
