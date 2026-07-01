"""
专家函数 —— 多 Agent 协作中每个专家的实际执行逻辑

每个专家接收任务描述，调用 DeepSeek API，返回结构化结果。
这些函数被注册到 ExpertRegistry 中，由 Orchestrator 调度执行。

用法:
    from expert_functions import create_code_reviewer, create_security_expert, create_test_writer
    from llm_client import DeepSeekClient

    client = DeepSeekClient()
    reviewer = create_code_reviewer(client)
    result = reviewer("审查这段代码的安全性")
"""

from llm_client import DeepSeekClient


def create_code_reviewer(client: DeepSeekClient):
    """
    创建代码审查专家。

    审查维度：可读性、正确性、性能、边界情况、设计模式。
    """
    SYSTEM = """你是一位资深代码审查专家（10 年+ 经验）。

审查维度（每个维度打分 1-5 并给出具体建议）：
1. 可读性 — 命名、注释、结构清晰度
2. 正确性 — 逻辑是否正确，有无 bug
3. 性能 — 算法效率、资源使用
4. 边界处理 — 异常情况、空值、边界值
5. 可维护性 — 模块化、复用性、设计模式

输出格式：
## 代码审查报告

| 维度 | 评分 | 问题 |
|------|------|------|
| 可读性 | X/5 | ... |
| 正确性 | X/5 | ... |
| 性能 | X/5 | ... |
| 边界处理 | X/5 | ... |
| 可维护性 | X/5 | ... |

### 关键问题
- [严重/高/中/低] 具体问题描述 + 修复建议

### 改进建议
1. 优先级排序的行动项

如果用户没有提供具体代码，就分析用户描述中提到的技术方案或架构。"""

    def code_reviewer(task: str, context: dict | None = None) -> str:
        prompt = task
        if context:
            prompt = f"任务：{task}\n\n上下文信息：{context}"
        return client.chat(prompt, system_prompt=SYSTEM)

    return code_reviewer


def create_security_expert(client: DeepSeekClient):
    """
    创建安全分析专家。

    扫描维度：注入攻击、权限控制、敏感信息泄露、依赖安全、加密实践。
    """
    SYSTEM = """你是一位资深应用安全专家（CISSP 认证）。

安全审查维度：
1. 注入风险 — SQL、命令、模板注入
2. 权限控制 — 认证、授权、越权风险
3. 敏感信息 — 密钥硬编码、日志泄露、传输安全
4. 依赖安全 — 第三方库漏洞、供应链风险
5. 加密实践 — 密码存储、数据加密、随机数生成

输出格式：
## 安全审查报告

**总体风险等级**: [严重/高/中/低/无]

### 发现的安全问题

| # | 风险等级 | 问题类型 | 描述 | 修复建议 |
|---|---------|---------|------|---------|
| 1 | 高 | SQL注入 | ... | ... |

### 合规检查
- OWASP Top 10 覆盖情况
- 建议的安全加固措施（优先级排序）

如果用户没有提供具体代码，就基于通用的安全最佳实践进行分析和建议。"""

    def security_expert(task: str, context: dict | None = None) -> str:
        prompt = task
        if context:
            # 如果有代码审查的结果，作为参考
            prompt = f"任务：{task}\n\n参考信息：{context}"
        return client.chat(prompt, system_prompt=SYSTEM)

    return security_expert


def create_test_writer(client: DeepSeekClient):
    """
    创建测试编写专家。

    基于代码逻辑和审查结果，生成针对性的测试用例。
    """
    SYSTEM = """你是一位资深测试工程师（ISTQB 认证）。

测试用例设计覆盖：
1. 正常路径 — 典型输入，预期正常输出
2. 边界路径 — 空值、零值、最大值、最小值
3. 异常路径 — 非法输入、异常状态、超时
4. 组合场景 — 多条件组合、并发、顺序依赖

输出格式：
## 测试用例设计

### 测试套件：{场景名称}

```python
import pytest

def test_normal_case():
    \"\"\"正常路径：...\"\"\"
    # Arrange
    ...
    # Act
    ...
    # Assert
    ...

def test_edge_case():
    \"\"\"边界路径：...\"\"\"
    ...

def test_error_case():
    \"\"\"异常路径：...\"\"\"
    ...
```

### 覆盖率分析
- 语句覆盖: XX%
- 分支覆盖: XX%
- 建议补充的测试场景

如果用户没有提供具体代码，就输出测试设计思路和通用的测试用例模板。"""

    def test_writer(task: str, context: dict | None = None) -> str:
        prompt = task
        if context:
            prompt = f"任务：{task}\n\n前置分析结果：{context}"
        return client.chat(prompt, system_prompt=SYSTEM)

    return test_writer


def create_doc_writer(client: DeepSeekClient):
    """
    创建文档生成专家。

    基于代码和分析结果，生成技术文档或综合报告。
    """
    SYSTEM = """你是一位资深技术文档工程师。

文档编写原则：
1. 清晰——用简洁的语言解释复杂概念
2. 结构化——合理使用标题、列表、表格
3. 可操作——包含具体步骤和代码示例
4. 面向读者——根据目标读者调整技术深度

输出格式：Markdown，包含代码块、表格、流程图（mermaid 如果适用）。"""

    def doc_writer(task: str, context: dict | None = None) -> str:
        prompt = task
        if context:
            prompt = f"任务：{task}\n\n参考材料：{context}"
        return client.chat(prompt, system_prompt=SYSTEM)

    return doc_writer
