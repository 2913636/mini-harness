"""
组件 3：会话存储（Session Store）

持久化对话状态，关了重开还能继续。
→ 对应 LangGraph Checkpoint
→ 对应 Claude Code 的会话恢复
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class Message:
    """一条消息

    v2 新增字段（多 Agent 支持）：
      - parent_id: 父消息 ID（树形结构），None=根节点
      - expert_id: 产生此消息的专家名称，空=编排者/用户
      - branch_id: 执行分支 ID，同一子任务的消息共享
    """
    role: str           # "user" | "assistant" | "system" | "tool" | "orchestrator" | "expert"
    content: str
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)
    parent_id: int | None = None
    expert_id: str = ""
    branch_id: str = ""

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp or time.time(),
            "metadata": self.metadata,
            "parent_id": self.parent_id,
            "expert_id": self.expert_id,
            "branch_id": self.branch_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            role=d["role"],
            content=d["content"],
            timestamp=d.get("timestamp", 0),
            metadata=d.get("metadata", {}),
            parent_id=d.get("parent_id"),
            expert_id=d.get("expert_id", ""),
            branch_id=d.get("branch_id", ""),
        )


@dataclass
class Session:
    """一个会话"""
    id: str
    messages: list[Message] = field(default_factory=list)
    state: dict = field(default_factory=dict)  # 自定义状态（如当前步骤、变量等）
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStore:
    """
    会话存储 —— 基于 SQLite 的对话持久化。

    职责：
      - 创建 / 加载 / 删除会话
      - 追加消息
      - 保存 / 读取自定义状态
      - 列出所有会话

    用法：
        store = SessionStore("sessions.db")
        session = store.create()
        store.add_message(session.id, Message(role="user", content="你好"))
        msgs = store.get_messages(session.id)
    """

    def __init__(self, db_path: str = ":memory:"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                state_json TEXT DEFAULT '{}',
                created_at REAL,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL,
                metadata_json TEXT DEFAULT '{}',
                parent_id INTEGER,
                expert_id TEXT DEFAULT '',
                branch_id TEXT DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_msg_branch ON messages(branch_id);
            CREATE INDEX IF NOT EXISTS idx_msg_expert ON messages(expert_id);
        """)
        self._conn.commit()

    # ── 会话 CRUD ───────────────────────

    def create(self, session_id: str | None = None) -> Session:
        """创建新会话"""
        import uuid
        sid = session_id or str(uuid.uuid4())[:8]
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions(id, state_json, created_at, updated_at) VALUES(?, ?, ?, ?)",
            (sid, "{}", now, now),
        )
        self._conn.commit()
        return Session(id=sid, created_at=now, updated_at=now)

    def get(self, session_id: str) -> Session | None:
        """加载会话"""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        msgs = self.get_messages(session_id)
        return Session(
            id=row["id"],
            messages=msgs,
            state=json.loads(row["state_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def delete(self, session_id: str):
        """删除会话及其消息"""
        self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    def list_sessions(self) -> list[dict]:
        """列出所有会话"""
        rows = self._conn.execute(
            "SELECT id, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [{"id": r["id"], "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]

    # ── 消息 CRUD ───────────────────────

    def add_message(self, session_id: str, message: Message):
        """追加一条消息"""
        now = time.time()
        self._conn.execute(
            "INSERT INTO messages(session_id, role, content, timestamp, metadata_json, parent_id, expert_id, branch_id) VALUES(?,?,?,?,?,?,?,?)",
            (
                session_id, message.role, message.content,
                message.timestamp or now,
                json.dumps(message.metadata, ensure_ascii=False),
                message.parent_id, message.expert_id, message.branch_id,
            ),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        self._conn.commit()

    def add_messages(self, session_id: str, messages: list[Message]):
        """批量追加消息"""
        now = time.time()
        for msg in messages:
            self._conn.execute(
                "INSERT INTO messages(session_id, role, content, timestamp, metadata_json, parent_id, expert_id, branch_id) VALUES(?,?,?,?,?,?,?,?)",
                (
                    session_id, msg.role, msg.content,
                    msg.timestamp or now,
                    json.dumps(msg.metadata, ensure_ascii=False),
                    msg.parent_id, msg.expert_id, msg.branch_id,
                ),
            )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        self._conn.commit()

    def get_messages(self, session_id: str, limit: int = 0) -> list[Message]:
        """获取会话消息（limit=0 表示全部）"""
        query = "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC"
        if limit > 0:
            query += f" LIMIT {limit}"
        rows = self._conn.execute(query, (session_id,)).fetchall()
        return [
            Message(
                role=r["role"],
                content=r["content"],
                timestamp=r["timestamp"],
                metadata=json.loads(r["metadata_json"]),
                parent_id=r["parent_id"],
                expert_id=r["expert_id"],
                branch_id=r["branch_id"],
            )
            for r in rows
        ]

    def get_messages_by_branch(self, session_id: str, branch_id: str) -> list[Message]:
        """按分支获取消息（v2 新增）"""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? AND branch_id = ? ORDER BY id ASC",
            (session_id, branch_id),
        ).fetchall()
        return [
            Message(
                role=r["role"],
                content=r["content"],
                timestamp=r["timestamp"],
                metadata=json.loads(r["metadata_json"]),
                parent_id=r["parent_id"],
                expert_id=r["expert_id"],
                branch_id=r["branch_id"],
            )
            for r in rows
        ]

    def get_messages_by_expert(self, session_id: str, expert_id: str) -> list[Message]:
        """按专家获取消息（v2 新增）"""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? AND expert_id = ? ORDER BY id ASC",
            (session_id, expert_id),
        ).fetchall()
        return [
            Message(
                role=r["role"],
                content=r["content"],
                timestamp=r["timestamp"],
                metadata=json.loads(r["metadata_json"]),
                parent_id=r["parent_id"],
                expert_id=r["expert_id"],
                branch_id=r["branch_id"],
            )
            for r in rows
        ]

    def get_message_tree(self, session_id: str) -> dict:
        """获取树形消息结构（v2 新增）
        Returns:
            {msg_id: {"msg": Message, "children": [child_ids]}}
        """
        msgs = self.get_messages(session_id)
        tree: dict = {}
        for m in msgs:
            # Use metadata to get a stable id, or fallback to index
            msg_id = m.metadata.get("msg_id", id(m))
            tree[msg_id] = {"msg": m, "children": []}

        # Build parent-child relationships
        for m in msgs:
            if m.parent_id is not None:
                parent = m.parent_id
                msg_id = m.metadata.get("msg_id", id(m))
                # Find parent by checking metadata
                for pid, node in tree.items():
                    pmsg = node["msg"]
                    if pmsg.metadata.get("msg_id") == parent:
                        node["children"].append(msg_id)
                        break

        return tree

    def get_message_count(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["cnt"]

    # ── 状态管理 ────────────────────────

    def save_state(self, session_id: str, state: dict):
        """保存自定义状态（如当前步骤、中间变量）"""
        self._conn.execute(
            "UPDATE sessions SET state_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(state, ensure_ascii=False), time.time(), session_id),
        )
        self._conn.commit()

    def get_state(self, session_id: str) -> dict:
        """读取自定义状态"""
        row = self._conn.execute(
            "SELECT state_json FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row:
            return json.loads(row["state_json"])
        return {}

    def close(self):
        self._conn.close()
