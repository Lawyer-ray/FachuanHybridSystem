"""CredentialPool 测试：轮询分配、并发上限、失败冷却。"""

import threading

from apps.document_parsing.services.credential_pool import CredentialPool, get_credential_pool


class TestCredentialPool:
    def test_empty_pool_acquires_none(self) -> None:
        pool = CredentialPool([])
        assert pool.acquire() is None

    def test_rotates_across_keys(self) -> None:
        pool = CredentialPool(["a", "b", "c"])
        idxs = [pool.acquire() for _ in range(3)]
        assert idxs == [0, 1, 2]
        # 全部 used→释放后可再次轮转
        for i in idxs:
            pool.release(i, success=True)
        assert pool.acquire() == 0

    def test_concurrency_limit(self) -> None:
        pool = CredentialPool(["a", "b"], concurrency_per_key=1)
        i0 = pool.acquire()
        i1 = pool.acquire()
        # a、b 各自被占用（每 key 上限 1）
        assert {i0, i1} == {0, 1}
        # 已满：超限使用下一个未冷却凭证（仍可用）
        assert pool.acquire() in (0, 1)
        pool.release(i0, success=True)
        pool.release(i1, success=True)

    def test_limit_zero_unlimited(self) -> None:
        pool = CredentialPool(["a"], concurrency_per_key=0)
        for _ in range(5):
            assert pool.acquire() == 0
        pool.release(0, success=True)

    def test_failed_credential_goes_cooldown(self, monkeypatch) -> None:
        pool = CredentialPool(["a", "b"])
        # 占用 a，失败后冷却
        idx = pool.acquire()
        assert idx == 0
        pool.release(idx, success=False)
        # b 立即可用
        assert pool.acquire() == 1
        pool.release(1, success=True)
        # a 仍在冷却 → 本轮轮询回到 a 但被跳过
        now = pool._failed_until[0]
        monkeypatch.setattr("apps.document_parsing.services.credential_pool.time.monotonic", lambda: now - 1)
        # 时间未到冷却结束，a 不可用；b 已被释放可用
        assert pool.acquire() == 1
        pool.release(1, success=True)

    def test_release_out_of_range_is_noop(self) -> None:
        pool = CredentialPool(["a"])
        pool.release(0, success=True)
        pool.release(99, success=True)  # 不抛错

    def test_thread_safety(self) -> None:
        pool = CredentialPool(["k"] * 4, concurrency_per_key=1)
        results: list[int] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                idx = pool.acquire()
                pool.release(idx, success=True)
                results.append(1)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert sum(results) == 20


class TestGetCredentialPool:
    def test_shares_same_pool_for_same_key(self) -> None:
        p1 = get_credential_pool("平台A", ["a"], 3)
        p2 = get_credential_pool("平台A", ["a"], 3)
        assert p1 is p2

    def test_rebuilds_when_credentials_change(self) -> None:
        p1 = get_credential_pool("平台B", ["a"], 3)
        p2 = get_credential_pool("平台B", ["a", "b"], 3)
        assert p1 is not p2
        assert p2.credentials == ["a", "b"]

    def test_rebuilds_when_limit_changes(self) -> None:
        p1 = get_credential_pool("平台C", ["a"], 3)
        p2 = get_credential_pool("平台C", ["a"], 5)
        assert p1 is not p2
        assert p2.limit == 5
