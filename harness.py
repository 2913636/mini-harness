"""从零搭建 Agent Harness — 工具注册+权限+日志+状态恢复"""
import time, json

class Harness:
    def __init__(self):
        self.tools, self.sessions, self.logs = {}, {}, []
    def register(self, name, fn, dangerous=False):
        self.tools[name] = {"fn": fn, "dangerous": dangerous}
    def run(self, session_id, tool_name, **kwargs):
        if session_id not in self.sessions: self.sessions[session_id] = {"checkpoints":[]}
        session = self.sessions[session_id]
        if tool_name not in self.tools: return f"工具不存在: {tool_name}"
        tool = self.tools[tool_name]
        if tool["dangerous"]:
            self.logs.append(f"[WARN] {tool_name} 需要确认"); return "需要人工确认"
        session["checkpoints"].append({"tool":tool_name,"args":kwargs,"time":time.time()})
        self.logs.append(f"[INFO] {tool_name}({kwargs})")
        return tool["fn"](**kwargs)

h = Harness()
h.register("add", lambda a,b: a+b)
h.register("delete_file", lambda path: f"已删除{path}", dangerous=True)

print(h.run("s1", "add", a=5, b=3))
print(h.run("s1", "delete_file", path="/tmp/x"))
print("Logs:", h.logs)
print("Checkpoints:", h.sessions["s1"]["checkpoints"])
