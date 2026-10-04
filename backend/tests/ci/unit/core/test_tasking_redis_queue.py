"""apps/core/tasking/redis_queue.py 单元测试。

全部通过 mock Django Q Conf / redis 客户端实现离线运行，
不依赖真实 Redis 连接。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.tasking import redis_queue
from apps.core.tasking.redis_queue import QueuedTask


def _signed_task(task_id: str, func: str = "apps.demo.tasks.run") -> str:
    """用 django_q SignedPackage 生成真实可反序列化的队列签名串。"""
    from django_q.signing import SignedPackage

    payload: dict[str, Any] = {
        "id": task_id,
        "name": f"task-{task_id}",
        "func": func,
        "args": (1, "x"),
        "kwargs": {"flag": True},
        "started": None,
    }
    return SignedPackage.dumps(payload)


class _FakeRedis:
    """极简 list 协议 fake，模拟 redis 客户端的队列操作。"""

    def __init__(self, items: list[str] | None = None) -> None:
        self.store: dict[str, list[bytes]] = {}
        if items:
            self.store["django_q:test_cluster:q"] = [i.encode("utf-8") for i in items]
        self.calls: list[str] = []

    def llen(self, key: str) -> int:
        self.calls.append(f"llen:{key}")
        return len(self.store.get(key, []))

    def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        self.calls.append(f"lrange:{key}:{start}:{end}")
        items = self.store.get(key, [])
        if end == -1:
            return list(items[start:])
        return list(items[start : end + 1])

    def lindex(self, key: str, index: int) -> bytes | None:
        items = self.store.get(key, [])
        if 0 <= index < len(items):
            return items[index]
        return None

    def lrem(self, key: str, count: int, value: bytes) -> int:
        items = self.store.get(key, [])
        removed = 0
        out: list[bytes] = []
        for it in items:
            if removed < count and it == value:
                removed += 1
                continue
            out.append(it)
        self.store[key] = out
        return removed

    def delete(self, key: str) -> int:
        self.calls.append(f"delete:{key}")
        existed = key in self.store
        self.store.pop(key, None)
        return 1 if existed else 0

    def rpush(self, key: str, *values: bytes) -> int:
        self.calls.append(f"rpush:{key}:{len(values)}")
        self.store.setdefault(key, []).extend(values)
        return len(self.store[key])


def _fake_conf(redis_url: str | None, cluster_name: str = "test_cluster") -> MagicMock:
    conf = MagicMock()
    conf.REDIS = redis_url
    conf.CLUSTER_NAME = cluster_name
    return conf


class TestIsRedisBroker:
    def test_true_when_redis_configured(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf("redis://localhost:6379/0")):
            assert redis_queue.is_redis_broker() is True

    def test_false_when_redis_missing(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf(None)):
            assert redis_queue.is_redis_broker() is False

    def test_false_when_redis_empty_string(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf("")):
            assert redis_queue.is_redis_broker() is False


class TestGetQueueKey:
    def test_key_contains_cluster_name(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf("redis://x", cluster_name="abc")):
            assert redis_queue._get_queue_key() == "django_q:abc:q"


class TestGetQueueLength:
    def test_returns_llen(self) -> None:
        fake = _FakeRedis(["a", "b"])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.get_queue_length() == 2
            mock_redis_cls.from_url.assert_called_once_with("redis://x")

    def test_zero_when_no_redis(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf(None)):
            assert redis_queue.get_queue_length() == 0


class TestListTasks:
    def test_empty_when_no_redis(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf(None)):
            assert redis_queue.list_tasks() == []

    def test_empty_queue(self) -> None:
        fake = _FakeRedis([])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.list_tasks() == []

    def test_deserializes_signed_tasks(self) -> None:
        raw = _signed_task("t-1")
        fake = _FakeRedis([raw])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            tasks = redis_queue.list_tasks()

        assert len(tasks) == 1
        task = tasks[0]
        assert isinstance(task, QueuedTask)
        assert task.index == 0
        assert task.task_id == "t-1"
        assert task.func == "apps.demo.tasks.run"
        assert task.args == (1, "x")
        assert task.kwargs == {"flag": True}
        assert task.started is None
        assert task.raw == raw

    def test_decode_error_entry_preserved(self) -> None:
        fake = _FakeRedis(["not-a-signed-payload", _signed_task("t-2")])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            tasks = redis_queue.list_tasks(limit=10)

        assert len(tasks) == 2
        assert tasks[0].task_id == "(decode error)"
        assert tasks[0].name == "(decode error)"
        assert tasks[0].func == ""
        assert tasks[1].task_id == "t-2"

    def test_limit_passed_to_lrange(self) -> None:
        raw = _signed_task("t-limit")
        fake = _FakeRedis([raw])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            redis_queue.list_tasks(limit=5)
        assert "lrange:django_q:test_cluster:q:0:4" in fake.calls

    def test_missing_fields_default(self) -> None:
        """签名字段缺失时使用默认值，而不是抛异常。"""
        from django_q.signing import SignedPackage

        raw = SignedPackage.dumps({"id": "only-id"})
        fake = _FakeRedis([raw])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            tasks = redis_queue.list_tasks()

        assert tasks[0].name == ""
        assert tasks[0].args == ()
        assert tasks[0].kwargs == {}


class TestDeleteTaskByIndex:
    def test_false_when_no_redis(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf(None)):
            assert redis_queue.delete_task_by_index(0) is False

    def test_false_when_index_out_of_range(self) -> None:
        fake = _FakeRedis([_signed_task("t-1")])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.delete_task_by_index(99) is False
            assert len(fake.store["django_q:test_cluster:q"]) == 1

    def test_removes_matching_raw(self) -> None:
        fake = _FakeRedis([_signed_task("t-1"), _signed_task("t-2")])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.delete_task_by_index(0) is True
        remaining = fake.store["django_q:test_cluster:q"]
        assert len(remaining) == 1

    def test_lrem_zero_returns_false(self) -> None:
        """lrem 返回 0（未删除任何元素）时应返回 False。"""
        fake = _FakeRedis([_signed_task("t-1")])
        fake.lrem = MagicMock(return_value=0)  # type: ignore[method-assign]
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.delete_task_by_index(0) is False


class TestDeleteTasksByIds:
    def test_zero_when_no_redis(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf(None)):
            assert redis_queue.delete_tasks_by_ids({"a"}) == 0

    def test_zero_when_queue_empty(self) -> None:
        fake = _FakeRedis([])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.delete_tasks_by_ids({"a"}) == 0

    def test_removes_only_requested_ids(self) -> None:
        keep1 = _signed_task("keep-1")
        drop1 = _signed_task("drop-1")
        keep2 = _signed_task("keep-2")
        fake = _FakeRedis([keep1, drop1, keep2])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            removed = redis_queue.delete_tasks_by_ids({"drop-1"})

        assert removed == 1
        remaining = fake.store["django_q:test_cluster:q"]
        assert len(remaining) == 2
        from django_q.signing import SignedPackage

        remaining_ids = {SignedPackage.loads(r.decode("utf-8"))["id"] for r in remaining}
        assert remaining_ids == {"keep-1", "keep-2"}

    def test_decode_error_task_is_kept_as_survivor(self) -> None:
        """无法反序列化的任务不应被误删。"""
        good = _signed_task("keep-1")
        fake = _FakeRedis(["corrupted!!", good])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            removed = redis_queue.delete_tasks_by_ids({"keep-1", "whatever"})

        assert removed == 1
        remaining = fake.store["django_q:test_cluster:q"]
        assert remaining == [b"corrupted!!"]

    def test_delete_all_leaves_key_absent(self) -> None:
        fake = _FakeRedis([_signed_task("a"), _signed_task("b")])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            removed = redis_queue.delete_tasks_by_ids({"a", "b"})

        assert removed == 2
        # 幸存者为空时不 rpush，key 保持删除状态
        assert "django_q:test_cluster:q" not in fake.store
        assert "rpush:" not in ",".join(fake.calls)


class TestPurgeQueue:
    def test_zero_when_no_redis(self) -> None:
        with patch("django_q.conf.Conf", _fake_conf(None)):
            assert redis_queue.purge_queue() == 0

    def test_purges_non_empty_queue(self) -> None:
        fake = _FakeRedis([_signed_task("a"), _signed_task("b"), _signed_task("c")])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.purge_queue() == 3
        assert "django_q:test_cluster:q" not in fake.store

    def test_empty_queue_returns_zero_without_delete(self) -> None:
        fake = _FakeRedis([])
        with (
            patch("django_q.conf.Conf", _fake_conf("redis://x")),
            patch("redis.Redis") as mock_redis_cls,
        ):
            mock_redis_cls.from_url.return_value = fake
            assert redis_queue.purge_queue() == 0
        assert "delete:django_q:test_cluster:q" not in fake.calls


class TestQueuedTaskDataclass:
    def test_fields_assigned(self) -> None:
        task = QueuedTask(
            index=3,
            task_id="tid",
            name="n",
            func="f",
            args=(1,),
            kwargs={"k": 1},
            started=None,
            raw="raw",
        )
        assert (task.index, task.task_id, task.func, task.raw) == (3, "tid", "f", "raw")


class TestNoRealRedisConnection:
    @pytest.mark.parametrize("func_name", ["get_queue_length", "list_tasks", "purge_queue"])
    def test_helpers_never_connect_when_broker_disabled(self, func_name: str) -> None:
        """REDIS 未配置时不得触碰 redis 模块。"""
        with (
            patch("django_q.conf.Conf", _fake_conf(None)),
            patch("redis.Redis") as mock_redis_cls,
        ):
            getattr(redis_queue, func_name)()
            mock_redis_cls.from_url.assert_not_called()
