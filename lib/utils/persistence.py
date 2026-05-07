from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from time import perf_counter

import anyio
import pydantic
from pydantic_graph import Graph, GraphRunResult, _utils as _graph_utils, exceptions
from pydantic_graph.nodes import BaseNode, DepsT, End
from pydantic_graph.persistence import (
    BaseStatePersistence,
    EndSnapshot,
    NodeSnapshot,
    RunEndT,
    Snapshot,
    SnapshotStatus,
    StateT,
    _utils,
    build_snapshot_list_type_adapter,
)

from lib.utils.common import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "db"


def get_persistance_db(
    task_type: str,
):
    if not DB_PATH.exists():
        DB_PATH.mkdir(parents=True, exist_ok=True)
    return DB_PATH / f"{task_type}.db"


async def run_persistent(
    graph: Graph[StateT, DepsT, RunEndT],
    start_node: BaseNode[StateT, DepsT, RunEndT],
    persistence: BaseStatePersistence[StateT, RunEndT],
    *,
    state: StateT = None,
    deps: DepsT = None,
    infer_name: bool = True,
    reset_error_or_running_snapshots: bool = False,
) -> GraphRunResult[StateT, RunEndT]:
    persistence.set_graph_types(graph)

    if reset_error_or_running_snapshots and isinstance(
        persistence, SQLite3StatePersistence
    ):
        await persistence.reset_error_or_running_snapshots()

    existing = await persistence.load_all()

    if not existing:
        await graph.initialize(
            start_node, persistence, state=state, infer_name=infer_name
        )
    else:
        end_snapshot = next(
            (s for s in reversed(existing) if isinstance(s, EndSnapshot)),
            None,
        )
        if end_snapshot is not None:
            print("Recover result from persistence")
            return GraphRunResult(
                output=end_snapshot.result.data,
                state=end_snapshot.state,
                persistence=persistence,
                traceparent=None,
            )
    if isinstance(persistence, SQLite3StatePersistence):
        print("Start running graph with persistence, run_id: ", persistence.run_id)

    async with graph.iter_from_persistence(
        persistence, deps=deps, infer_name=infer_name
    ) as graph_run:
        async for _ in graph_run:
            pass

    result = graph_run.result

    assert result is not None, (
        "GraphRun should have a result by now, or else raised an Exception."  # Mimic Graph.run method implementation
    )

    return result


@dataclass
class SQLite3StatePersistence(BaseStatePersistence[StateT, RunEndT]):
    db_path: Path
    run_id: str

    lock: anyio.Lock = field(default_factory=anyio.Lock)

    _snapshots_type_adapter: (
        pydantic.TypeAdapter[list[Snapshot[StateT, RunEndT]]] | None
    ) = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._init_db()

    async def snapshot_node(
        self, state: StateT, next_node: BaseNode[StateT, DepsT, RunEndT]
    ) -> None:
        await self._append_save(NodeSnapshot(state=state, node=next_node))

    async def snapshot_node_if_new(
        self,
        snapshot_id: str,
        state: StateT,
        next_node: BaseNode[StateT, DepsT, RunEndT],
    ) -> None:
        snapshots = await self.load_all()
        if not any(s.id == snapshot_id for s in snapshots):
            await self._append_save(NodeSnapshot(state=state, node=next_node))

    async def snapshot_end(self, state: StateT, end: End[RunEndT]) -> None:
        await self._append_save(EndSnapshot(state=state, result=end))

    @asynccontextmanager
    async def record_run(self, snapshot_id: str) -> AsyncIterator[None]:
        snapshots = await self.load_all()
        try:
            snapshot = next(s for s in snapshots if s.id == snapshot_id)
        except StopIteration as e:
            raise LookupError(f"No snapshot found with id={snapshot_id!r}") from e

        assert isinstance(snapshot, NodeSnapshot), "Only NodeSnapshot can be recorded"
        exceptions.GraphNodeStatusError.check(snapshot.status)
        snapshot.status = "running"
        snapshot.start_ts = _utils.now_utc()
        await self._save(snapshots)

        start = perf_counter()
        try:
            yield
        except Exception:
            duration = perf_counter() - start
            await _graph_utils.run_in_executor(
                self._after_run_sync, snapshot_id, duration, "error"
            )
            raise
        else:
            snapshot.duration = perf_counter() - start
            await _graph_utils.run_in_executor(
                self._after_run_sync, snapshot_id, snapshot.duration, "success"
            )

    async def load_next(self) -> NodeSnapshot | None:
        snapshots = await self.load_all()
        if snapshot := next(
            (
                s
                for s in snapshots
                if isinstance(s, NodeSnapshot) and s.status == "created"
            ),
            None,
        ):
            snapshot.status = "pending"
            await self._save(snapshots)
            return snapshot

    def should_set_types(self) -> bool:
        """Whether types need to be set."""
        return self._snapshots_type_adapter is None

    def set_types(self, state_type: type[StateT], run_end_type: type[RunEndT]) -> None:
        self._snapshots_type_adapter = build_snapshot_list_type_adapter(
            state_type, run_end_type
        )

    async def reset_error_or_running_snapshots(self) -> None:
        snapshots = await self.load_all()
        changed = False
        for snapshot in snapshots:
            if isinstance(snapshot, NodeSnapshot) and snapshot.status in {
                "pending",
                "running",
                "error",
            }:
                snapshot.status = "created"
                changed = True
        if changed:
            await self._save(snapshots)

    async def load_all(self) -> list[Snapshot[StateT, RunEndT]]:
        return await _graph_utils.run_in_executor(self._load_sync)

    def _load_sync(self) -> list[Snapshot[StateT, RunEndT]]:
        assert self._snapshots_type_adapter is not None, (
            "snapshots type adapter must be set"
        )
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            row = conn.execute(
                "SELECT snapshots FROM graph_runs WHERE run_id = ?", (self.run_id,)
            ).fetchone()
        if row is None:
            return []
        return self._snapshots_type_adapter.validate_json(row[0])

    def _after_run_sync(
        self, snapshot_id: str, duration: float, status: SnapshotStatus
    ) -> None:
        snapshots = self._load_sync()
        snapshot = next(s for s in snapshots if s.id == snapshot_id)
        assert isinstance(snapshot, NodeSnapshot), "Only NodeSnapshot can be recorded"
        snapshot.duration = duration
        snapshot.status = status
        self._save_sync(snapshots)

    async def _save(self, snapshots: list[Snapshot[StateT, RunEndT]]) -> None:
        async with self.lock:
            await _graph_utils.run_in_executor(self._save_sync, snapshots)

    def _save_sync(self, snapshots: list[Snapshot[StateT, RunEndT]]) -> None:
        assert self._snapshots_type_adapter
        json_data = self._snapshots_type_adapter.dump_json(snapshots).decode()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO graph_runs (run_id, snapshots)
                    VALUES (?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET snapshots = excluded.snapshots;
                """,
                    (self.run_id, json_data),
                )

    async def _append_save(self, snapshot: Snapshot[StateT, RunEndT]) -> None:
        assert self._snapshots_type_adapter is not None, (
            "snapshots type adapter must be set"
        )

        snapshots = await self.load_all()
        snapshots.append(snapshot)
        await self._save(snapshots)

    def _init_db(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=30000;")
                conn.execute("PRAGMA temp_store=MEMORY;")
                conn.execute("PRAGMA mmap_size=268435456;")
                conn.execute("PRAGMA cache_size=2000;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS graph_runs (
                        run_id TEXT PRIMARY KEY,
                        snapshots TEXT NOT NULL
                    );
                """)
