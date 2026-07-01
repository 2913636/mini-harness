"""mini-harness 命令行入口

用法：
    python -m harness              # 交互模式
    python -m harness --demo       # 运行 v1 演示
    python -m harness --demo-v2    # 运行 v2 多 Agent 演示
"""

import sys


def main():
    if "--demo-v2" in sys.argv:
        print(">>> 启动 v2 多 Agent 演示模式...")
        try:
            import demo_v2
            demo_v2.main()
        except ImportError as e:
            print(f"错误：无法导入 demo_v2 — {e}")
            print("请确保已安装依赖：pip install -r requirements.txt")
    elif "--demo" in sys.argv:
        print(">>> 启动 v1 单 Agent 演示模式...")
        try:
            import demo
            demo.main()
        except ImportError as e:
            print(f"错误：无法导入 demo — {e}")
    else:
        print("mini-harness — Agent 运行时框架")
        print(f"  Python {sys.version.split()[0]}")
        print()
        print("用法：")
        print("  python -m harness --demo      运行 v1 单 Agent 演示")
        print("  python -m harness --demo-v2   运行 v2 多 Agent 演示")
        print()
        print("在代码中使用：")
        print("  from harness import AgentHarness")
        print("  harness = AgentHarness()")
        print("  harness.set_llm(your_llm_fn)")
        print("  result = harness.run('你的任务')")


if __name__ == "__main__":
    main()
