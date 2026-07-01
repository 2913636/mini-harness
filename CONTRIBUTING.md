# 贡献指南

感谢你对 mini-harness 的关注！以下是参与项目的方式。

## 快速开始

```bash
git clone https://github.com/2913636/mini-harness.git
cd mini-harness
pip install -r requirements.txt
py demo.py        # 单 Agent 演示
py demo_v2.py     # 多 Agent 演示
```

## 开发流程

1. **Fork 并 Clone** 仓库
2. **创建分支**：`git checkout -b feat/your-feature`
3. **编写代码 + 测试**
4. **运行检查**：
   ```bash
   ruff check harness/ --ignore E501
   mypy harness/ --ignore-missing-imports
   pytest tests/ -v
   ```
5. **提交 PR** 到 `master` 分支

## 代码风格

- Python 3.10+ 兼容
- 使用 type hints
- 文档字符串：关键方法用 docstring
- 命名：snake_case 变量/函数，PascalCase 类

## 项目架构

```
harness/
├── tool_registry.py   # 组件 1：工具注册表
├── permission.py      # 组件 2：权限门禁
├── session.py         # 组件 3：会话存储
├── compressor.py      # 组件 4：上下文压缩
├── tracer.py          # 组件 5：日志追踪
├── recovery.py        # 组件 6：恢复机制
├── expert.py          # 组件 7：专家注册表 (v2)
├── orchestrator.py    # 组件 9：编排者引擎 (v2)
├── synthesizer.py     # 组件 8：结果合成器 (v2)
└── harness.py         # 统一入口 AgentHarness
```

详见 [README.md](README.md) 中的架构图。

## 添加新组件

1. 在 `harness/` 下创建 `your_component.py`
2. 在 `harness/__init__.py` 中导出公共 API
3. 在 `harness/harness.py` 的 `AgentHarness` 中集成
4. 写单元测试 `tests/test_your_component.py`
5. 如果需要，添加 ADR 到 `docs/decisions/`

## 测试

测试框架：pytest。测试文件放在 `tests/` 目录。

```bash
pytest tests/ -v --tb=short
```

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。
