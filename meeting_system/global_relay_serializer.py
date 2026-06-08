"""
global_relay_serializer — 複数プロジェクト並行のシングルスレッド順次リレー

3者合意 (前議題 R50-MULTI-PROJECT-PARALLEL-AND-BROWSER-CHECK):
- asyncio.PriorityQueue + asyncio.Lock 二段防御
- queue_priority (小さいほど先) + FIFO _counter で決定論的順序
- 1AI発言完了ごとスロット解放 → 次ルーム
- PCフリーズ防止の物理境界線
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class GlobalRelaySerializer:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._counter = 0

    async def enqueue(self, room_id: str, priority: int = 5) -> None:
        self._counter += 1
        await self._queue.put((priority, self._counter, room_id))

    @asynccontextmanager
    async def acquire_slot(self) -> AsyncIterator[str]:
        priority, _seq, room_id = await self._queue.get()
        async with self._lock:
            try:
                yield room_id
            finally:
                self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()


async def _async_self_test() -> bool:
    s = GlobalRelaySerializer()
    await s.enqueue("low_room", priority=10)
    await s.enqueue("high_room", priority=1)
    await s.enqueue("mid_room", priority=5)

    order: list[str] = []
    for _ in range(3):
        async with s.acquire_slot() as room_id:
            order.append(room_id)

    assert order[0] == "high_room", f"priority 1 should come first: {order}"
    assert order[1] == "mid_room"
    assert order[2] == "low_room"

    s2 = GlobalRelaySerializer()
    await s2.enqueue("a", 5)
    await s2.enqueue("b", 5)
    await s2.enqueue("c", 5)
    order2: list[str] = []
    for _ in range(3):
        async with s2.acquire_slot() as room_id:
            order2.append(room_id)
    assert order2 == ["a", "b", "c"], f"FIFO violation: {order2}"

    print("PASS: global_relay_serializer self_test (priority + FIFO)")
    return True


def self_test() -> bool:
    return asyncio.run(_async_self_test())


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
