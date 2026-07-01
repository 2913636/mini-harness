"""
组件 5：日志追踪（Logger / Tracer）

每一步发生了什么——调了什么工具、花了多少 token、耗时多少、有没有报错。
→ 对应 LangChain 的 @traceable 装饰器
→ 对应 LangSmith / LangFuse 追踪平台
"""

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Optional


@dataclass
class TraceStep:
    """一步操作的追踪记录"""
    step_id: str
    step_type: str       # "llm_call" | "tool_call" | "gate_check" | "compress" | "recovery" | "orchestrate" | "expert_call" | "synthesize" | "decompose"
    session_id: str = ""
    input_summary: str = ""      # 输入的摘要（不存完整内容，防日志爆炸）
    output_summary: str = ""     # 输出的摘要
    token_used: int = 0
    duration_ms: float = 0.0
    error: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0
    # v2 多 Agent 新增
    expert_id: str = ""          # 属于哪个专家
    parent_step_id: str = ""     # 父步骤 ID（因果链）


class Tracer:
    """
    日志追踪器 —— 结构化记录 Agent 每一步操作。

    存储：
      - SQLite 持久化（可查询、可统计）
      - 控制台实时输出（可观察）

    用法：
        tracer = Tracer("trace.db")

        with tracer.span("tool_call", session_id="abc") as step:
            result = some_tool()
            step.output_summary = str(result)[:200]
            # 自动记录耗时
        # 离开 with 块时自动写入
    """

    def __init__(self, db_path: str = ":memory:", verbose: bool = True):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.verbose = verbose
        self._init_tables()

    def _init_tables(self):
        self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS traces (
                step_id TEXT PRIMARY KEY,
                step_type TEXT NOT NULL,
                session_id TEXT DEFAULT '',
                input_summary TEXT DEFAULT '',
                output_summary TEXT DEFAULT '',
                token_used INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0,
                error TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                timestamp REAL,
                expert_id TEXT DEFAULT '',
                parent_step_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_trace_session ON traces(session_id);
            CREATE INDEX IF NOT EXISTS idx_trace_type ON traces(step_type);
            CREATE INDEX IF NOT EXISTS idx_trace_expert ON traces(expert_id);
            CREATE INDEX IF NOT EXISTS idx_trace_parent ON traces(parent_step_id);
        """)
        self._conn.commit()

    # ── 上下文管理器（推荐用法）──────────

    @contextmanager
    def span(self, step_type: str, session_id: str = "", **meta):
        """
        追踪一个操作。

        Yields:
            TraceStep 对象，你可以在 with 块内修改它。

        Example:
            with tracer.span("llm_call", session_id="abc") as step:
                response = call_llm(messages)
                step.token_used = response.usage.total_tokens
                step.output_summary = response.content[:200]
        """
        import uuid
        step = TraceStep(
            step_id=str(uuid.uuid4())[:8],
            step_type=step_type,
            session_id=session_id,
            metadata=meta,
            timestamp=time.time(),
        )
        t0 = time.perf_counter()
        try:
            yield step
        except Exception as e:
            step.error = str(e)[:500]
            raise
        finally:
            step.duration_ms = (time.perf_counter() - t0) * 1000
            self._write(step)
            if self.verbose:
                self._print(step)

    # ── 快速记录（不用 with）─────────────

    def record(
        self,
        step_type: str,
        session_id: str = "",
        input_summary: str = "",
        output_summary: str = "",
        token_used: int = 0,
        duration_ms: float = 0,
        error: str = "",
        expert_id: str = "",
        parent_step_id: str = "",
        **meta,
    ) -> TraceStep:
        """快速记录一条追踪"""
        import uuid
        step = TraceStep(
            step_id=str(uuid.uuid4())[:8],
            step_type=step_type,
            session_id=session_id,
            input_summary=input_summary,
            output_summary=output_summary,
            token_used=token_used,
            duration_ms=duration_ms,
            error=error,
            metadata=meta,
            timestamp=time.time(),
            expert_id=expert_id,
            parent_step_id=parent_step_id,
        )
        self._write(step)
        if self.verbose:
            self._print(step)
        return step

    # ── 写入 / 打印 ─────────────────────

    def _write(self, step: TraceStep):
        with self._lock:
            self._conn.execute(
                """INSERT INTO traces(step_id, step_type, session_id, input_summary,
                   output_summary, token_used, duration_ms, error, metadata_json, timestamp,
                   expert_id, parent_step_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    step.step_id, step.step_type, step.session_id,
                    step.input_summary[:500], step.output_summary[:500],
                    step.token_used, step.duration_ms, step.error,
                    json.dumps(step.metadata, ensure_ascii=False),
                    step.timestamp,
                    step.expert_id, step.parent_step_id,
                ),
            )
            self._conn.commit()

    # 敏感数据模式：匹配这些模式的值将自动脱敏
    _SENSITIVE_PATTERNS = [
        "api_key", "apikey", "api_secret", "secret", "password",
        "token", "credential", "private_key", "access_key",
    ]

    @classmethod
    def _redact_sensitive(cls, text: str) -> str:
        """对可能包含敏感数据的摘要文本进行脱敏。

        覆盖模式：
          - key=value / key: value （明文配置）
          - "key": "value" / "key": value （JSON 格式）
        """
        if not text:
            return text
        import re
        for pattern in cls._SENSITIVE_PATTERNS:
            # 模式 1: key=value 或 key: value（无引号/明文格式）
            text = re.sub(
                rf'({pattern}\s*[=:]\s*)(\S+)',
                r'\1[REDACTED]',
                text,
                flags=re.IGNORECASE,
            )
            # 模式 2: "key": "value" 或 "key": value（JSON 格式）
            text = re.sub(
                rf'(["\']({pattern})["\']\s*:\s*)(["\']?)([^"\'\,\s\}}]+)(\3)',
                r'\1\3[REDACTED]\5',
                text,
                flags=re.IGNORECASE,
            )
        return text

    def _print(self, step: TraceStep):
        """控制台输出格式"""
        icons = {
            "llm_call": "[LLM]",
            "tool_call": "[TOOL]",
            "gate_check": "[GATE]",
            "compress": "[COMPRESS]",
            "recovery": "[RECOVER]",
            "orchestrate": "[ORCH]",
            "expert_call": "[EXP]",
            "synthesize": "[SYNTH]",
            "decompose": "[DECOMP]",
        }
        icon = icons.get(step.step_type, "[*]")
        status = " [ERR]" if step.error else ""

        parts = [
            f"{icon} [{step.step_type.upper()}]{status}",
        ]
        if step.expert_id:
            parts.append(f"expert={step.expert_id}")
        if step.token_used:
            parts.append(f"token={step.token_used}")
        if step.duration_ms:
            parts.append(f"{step.duration_ms:.0f}ms")
        if step.input_summary:
            parts.append(f"-> {self._redact_sensitive(step.input_summary[:80])}")
        if step.error:
            parts.append(f"err={self._redact_sensitive(step.error[:60])}")

        print(" | ".join(parts))

    # ── 查询（调试/统计用）───────────────

    def query(
        self,
        session_id: str = "",
        step_type: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """查询追踪记录"""
        conditions = []
        params = []
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if step_type:
            conditions.append("step_type = ?")
            params.append(step_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._conn.execute(
            f"SELECT * FROM traces WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self, session_id: str = "") -> dict:
        """统计摘要"""
        cond = "WHERE session_id = ?" if session_id else ""
        params = [session_id] if session_id else []

        total = self._conn.execute(
            f"SELECT COUNT(*) as cnt FROM traces {cond}", params
        ).fetchone()["cnt"]

        total_tokens = self._conn.execute(
            f"SELECT SUM(token_used) as total FROM traces {cond}", params
        ).fetchone()["total"] or 0

        total_time = self._conn.execute(
            f"SELECT SUM(duration_ms) as total FROM traces {cond}", params
        ).fetchone()["total"] or 0

        errors = self._conn.execute(
            f"SELECT COUNT(*) as cnt FROM traces {cond} {'AND' if cond else 'WHERE'} error != ''", params
        ).fetchone()["cnt"]

        return {
            "total_steps": total,
            "total_tokens": total_tokens,
            "total_time_ms": total_time,
            "errors": errors,
        }

    def query_by_expert(self, expert_id: str, limit: int = 50) -> list[dict]:
        """按专家查询追踪记录（v2 新增）"""
        rows = self._conn.execute(
            "SELECT * FROM traces WHERE expert_id = ? ORDER BY timestamp DESC LIMIT ?",
            (expert_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_causal_chain(self, step_id: str) -> list[dict]:
        """查询某个步骤的因果链（v2 新增）"""
        chain = []
        current = step_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            row = self._conn.execute(
                "SELECT * FROM traces WHERE step_id = ?", (current,)
            ).fetchone()
            if row:
                chain.append(dict(row))
                current = row["parent_step_id"]
            else:
                break
        return chain

    def expert_stats(self, session_id: str = "") -> list[dict]:
        """按专家统计性能（v2 新增）"""
        cond = "WHERE session_id = ? AND expert_id != ''" if session_id else "WHERE expert_id != ''"
        params = [session_id] if session_id else []

        rows = self._conn.execute(
            f"""SELECT expert_id,
                       COUNT(*) as calls,
                       SUM(token_used) as total_tokens,
                       SUM(duration_ms) as total_ms,
                       SUM(CASE WHEN error != '' THEN 1 ELSE 0 END) as errors
                FROM traces {cond}
                GROUP BY expert_id
                ORDER BY calls DESC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
