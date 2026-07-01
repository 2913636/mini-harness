"""组件 3: SessionStore 单元测试"""

import os
import pytest
from harness.session import SessionStore, Session, Message


class TestMessage:
    def test_create_message(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"
        assert m.parent_id is None
        assert m.expert_id == ""
        assert m.branch_id == ""

    def test_message_to_dict(self):
        m = Message(role="assistant", content="hi", expert_id="coder", branch_id="b1")
        d = m.to_dict()
        assert d["role"] == "assistant"
        assert d["expert_id"] == "coder"
        assert d["branch_id"] == "b1"

    def test_message_from_dict(self):
        d = {"role": "user", "content": "test", "parent_id": 5, "expert_id": "exp1"}
        m = Message.from_dict(d)
        assert m.role == "user"
        assert m.parent_id == 5
        assert m.expert_id == "exp1"

    def test_message_v2_fields(self):
        m = Message(role="expert", content="result", parent_id=3, expert_id="coder", branch_id="b2")
        d = m.to_dict()
        m2 = Message.from_dict(d)
        assert m2.parent_id == 3
        assert m2.expert_id == "coder"
        assert m2.branch_id == "b2"


class TestSession:
    def test_create_session(self):
        s = Session(id="abc")
        assert s.id == "abc"
        assert s.messages == []
        assert s.state == {}

    def test_session_to_dict(self):
        m = Message(role="user", content="hi")
        s = Session(id="s1", messages=[m], state={"step": 1})
        d = s.to_dict()
        assert d["id"] == "s1"
        assert len(d["messages"]) == 1
        assert d["state"]["step"] == 1


class TestSessionStore:
    @pytest.fixture
    def store(self):
        """使用内存数据库避免文件残留"""
        s = SessionStore(":memory:")
        yield s
        s.close()

    def test_create_session(self, store):
        session = store.create()
        assert session.id is not None
        assert len(session.messages) == 0

    def test_create_with_custom_id(self, store):
        session = store.create("my-session")
        assert session.id == "my-session"

    def test_get_existing(self, store):
        store.create("s1")
        s = store.get("s1")
        assert s is not None
        assert s.id == "s1"

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None

    def test_add_and_get_messages(self, store):
        s = store.create()
        store.add_message(s.id, Message(role="user", content="hello"))
        store.add_message(s.id, Message(role="assistant", content="hi there"))
        msgs = store.get_messages(s.id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_add_messages_batch(self, store):
        s = store.create()
        msgs = [
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
        ]
        store.add_messages(s.id, msgs)
        assert store.get_message_count(s.id) == 3

    def test_get_messages_with_limit(self, store):
        s = store.create()
        for i in range(10):
            store.add_message(s.id, Message(role="user", content=f"msg{i}"))
        msgs = store.get_messages(s.id, limit=3)
        assert len(msgs) == 3

    def test_delete_session(self, store):
        s = store.create()
        store.add_message(s.id, Message(role="user", content="test"))
        store.delete(s.id)
        assert store.get(s.id) is None
        assert store.get_message_count(s.id) == 0

    def test_list_sessions(self, store):
        store.create("a")
        store.create("b")
        sessions = store.list_sessions()
        assert len(sessions) == 2

    def test_save_and_get_state(self, store):
        s = store.create()
        store.save_state(s.id, {"step": 3, "mode": "review"})
        state = store.get_state(s.id)
        assert state["step"] == 3
        assert state["mode"] == "review"

    def test_get_state_empty(self, store):
        s = store.create()
        assert store.get_state(s.id) == {}

    def test_message_count(self, store):
        s = store.create()
        assert store.get_message_count(s.id) == 0
        store.add_message(s.id, Message(role="user", content="a"))
        store.add_message(s.id, Message(role="user", content="b"))
        assert store.get_message_count(s.id) == 2

    def test_v2_fields_persisted(self, store):
        s = store.create()
        m = Message(role="expert", content="code review done", parent_id=1, expert_id="coder", branch_id="b1")
        store.add_message(s.id, m)
        msgs = store.get_messages(s.id)
        assert len(msgs) == 1
        assert msgs[0].expert_id == "coder"
        assert msgs[0].branch_id == "b1"
        assert msgs[0].parent_id == 1

    def test_get_messages_by_branch(self, store):
        s = store.create()
        store.add_message(s.id, Message(role="expert", content="r1", branch_id="b1"))
        store.add_message(s.id, Message(role="expert", content="r2", branch_id="b1"))
        store.add_message(s.id, Message(role="expert", content="r3", branch_id="b2"))
        b1_msgs = store.get_messages_by_branch(s.id, "b1")
        assert len(b1_msgs) == 2
        b2_msgs = store.get_messages_by_branch(s.id, "b2")
        assert len(b2_msgs) == 1

    def test_get_messages_by_expert(self, store):
        s = store.create()
        store.add_message(s.id, Message(role="expert", content="r1", expert_id="coder"))
        store.add_message(s.id, Message(role="expert", content="r2", expert_id="coder"))
        store.add_message(s.id, Message(role="expert", content="r3", expert_id="security"))
        coder_msgs = store.get_messages_by_expert(s.id, "coder")
        assert len(coder_msgs) == 2

    def test_get_message_tree(self, store):
        """Test tree structure with parent-child relationships"""
        s = store.create()
        # Root message
        store.add_message(s.id, Message(role="user", content="task", parent_id=None))
        # Get the db_id from the stored message
        all_msgs = store.get_messages(s.id)
        root_db_id = all_msgs[0].metadata["db_id"]

        # Child referencing parent
        store.add_message(s.id, Message(role="expert", content="result", parent_id=root_db_id, branch_id="b1"))

        tree = store.get_message_tree(s.id)
        assert len(tree) >= 2
        # Verify parent has children
        parent_node = tree[root_db_id]
        assert len(parent_node["children"]) > 0

    def test_db_id_in_metadata(self, store):
        """Verify db_id is stored in metadata for stable identification"""
        s = store.create()
        store.add_message(s.id, Message(role="user", content="test"))
        msgs = store.get_messages(s.id)
        assert "db_id" in msgs[0].metadata
        assert isinstance(msgs[0].metadata["db_id"], int)
