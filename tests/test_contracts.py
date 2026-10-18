"""跨组兼容与数据契约测试（对应外部评审 H1/H2/M1/L1）。

覆盖点：
* H1：画布能读 P1/P2 的 ``sid`` 字段，以及 dict 形式 stations 的 key 回退；
* H2：``events`` 支持 ``(kind, sid)`` 元组 / 字典 / 纯 ID 列表三种写法；
* M1：per-line ``speed_kmh`` 生效，``weight="distance"`` 与 ``time`` 结果不同但正确；
* L1：JSON/TXT 里的重复站点/线路 ID 必须抛 ``DataFormatError``，不能静默覆盖。

只依赖标准库；画布模块只 import tkinter，不创建窗口。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import DataFormatError, load_dataset, solve  # noqa: E402
from ui.canvas import normalise_graph, normalise_result  # noqa: E402

SMOKE = ROOT / "_smoke"


# ----------------------------------------------------------------------
# P1/P2 风格的假对象（字段名用 sid，而不是本项目当前的 id）
# ----------------------------------------------------------------------
class SidStation:
    def __init__(self, sid: str, name: str, x: float, y: float) -> None:
        self.sid = sid
        self.name = name
        self.x = x
        self.y = y


class SidLine:
    def __init__(self, sid: str, name: str, stations: list[str]) -> None:
        self.sid = sid
        self.name = name
        self.color = "#2563EB"
        self.loop = False
        self.stations = stations


class SidGraph:
    speed_kmh = 35.0
    dwell_minutes = 0.6

    def __init__(self) -> None:
        self.stations = [
            SidStation("S1", "甲", 0.0, 0.0),
            SidStation("S2", "乙", 1.0, 0.0),
            SidStation("S3", "丙", 2.0, 0.0),
        ]
        self.lines = [SidLine("L1", "一号线", ["S1", "S2", "S3"])]


class FakeResult:
    """任务书风格的结果：path/events 用 P2 的 (kind, sid) 写法。"""

    def __init__(self, events: list, stations: list[str]) -> None:
        self.found = True
        self.algorithm = "Dijkstra"
        self.path = stations
        self.stations = stations
        self.events = events
        self.distance_km = 2.0
        self.time_min = 4.0
        self.transfers = 0
        self.expanded = 2
        self.message = "ok"


class CanvasCompatTests(unittest.TestCase):
    def test_graph_accepts_sid_field(self) -> None:
        draw = normalise_graph(SidGraph())
        self.assertEqual(sorted(draw.stations), ["S1", "S2", "S3"])
        self.assertEqual(draw.stations["S1"].name, "甲")
        self.assertEqual(len(draw.lines), 1)

    def test_graph_dict_stations_falls_back_to_key(self) -> None:
        graph = SimpleNamespace(
            stations={
                "S1": SimpleNamespace(name="甲", x=0.0, y=0.0),
                "S2": SimpleNamespace(name="乙", x=1.0, y=0.0),
            },
            lines=[
                SimpleNamespace(
                    id="L1", name="一号线", color="#2563EB",
                    loop=False, stations=["S1", "S2"],
                )
            ],
        )
        draw = normalise_graph(graph)
        self.assertEqual(sorted(draw.stations), ["S1", "S2"])

    def test_events_accept_kind_sid_tuples(self) -> None:
        graph = SidGraph()
        draw = normalise_graph(graph)
        result = FakeResult(
            events=[("settle", "S1"), ("settle", "S2"), ("push", "S3")],
            stations=["S1", "S2", "S3"],
        )
        view = normalise_result(graph, draw, result)
        self.assertEqual(view.events, ["S1", "S2", "S3"])
        self.assertNotIn("settle", view.events)

    def test_events_accept_dicts_and_plain_ids(self) -> None:
        graph = SidGraph()
        draw = normalise_graph(graph)
        result = FakeResult(
            events=[{"kind": "settle", "sid": "S1"}, "S2", ("S3", "L1")],
            stations=["S1", "S2", "S3"],
        )
        view = normalise_result(graph, draw, result)
        self.assertEqual(view.events, ["S1", "S2", "S3"])

    def test_result_station_objects_with_sid(self) -> None:
        graph = SidGraph()
        draw = normalise_graph(graph)
        result = FakeResult(events=[], stations=[])
        result.stations = [SidStation("S1", "甲", 0, 0), SidStation("S2", "乙", 1, 0)]
        view = normalise_result(graph, draw, result)
        self.assertEqual(view.stations, ["S1", "S2"])


class EdgeFallbackTests(unittest.TestCase):
    """线条目没有 stations 时，从 graph.edges 反推站序（只给边表的图也能画）。"""

    @staticmethod
    def _graph(lines, edges):
        stations = [
            SidStation("S1", "甲", 0.0, 0.0),
            SidStation("S2", "乙", 1.0, 0.0),
            SidStation("S3", "丙", 2.0, 0.0),
            SidStation("S4", "丁", 3.0, 0.0),
        ]
        return SimpleNamespace(stations=stations, lines=lines, edges=edges)

    def test_line_without_stations_derives_order_from_edges(self) -> None:
        line = SimpleNamespace(id="L1", name="一号线", color="#2563EB", loop=False)
        edges = [
            {"from": "S2", "to": "S3", "line_id": "L1"},
            {"from": "S1", "to": "S2", "line_id": "L1"},
        ]
        draw = normalise_graph(self._graph([line], edges))
        self.assertEqual(draw.lines[0].station_ids, ("S1", "S2", "S3"))
        self.assertEqual(draw.station_lines["S2"], ["L1"])

    def test_explicit_stations_have_priority(self) -> None:
        line = SimpleNamespace(
            id="L1", name="一号线", color="#2563EB", loop=False,
            stations=["S2", "S1"],
        )
        edges = [{"from": "S1", "to": "S2", "line_id": "L1"}]
        draw = normalise_graph(self._graph([line], edges))
        self.assertEqual(draw.lines[0].station_ids, ("S2", "S1"))

    def test_edges_without_line_id_used_only_for_single_line_graph(self) -> None:
        line = SimpleNamespace(id="L1", name="一号线", color="#2563EB", loop=False)
        edges = [("S1", "S2"), ("S2", "S3")]  # 元组、没有 line_id
        draw = normalise_graph(self._graph([line], edges))
        self.assertEqual(draw.lines[0].station_ids, ("S1", "S2", "S3"))

    def test_attribute_style_edges_supported(self) -> None:
        line = SimpleNamespace(id="L1", name="一号线", color="#2563EB", loop=False)
        edges = [
            SimpleNamespace(from_station="S1", to_station="S2", line_id="L1"),
            SimpleNamespace(from_station="S2", to_station="S3", line_id="L1"),
        ]
        draw = normalise_graph(self._graph([line], edges))
        self.assertEqual(draw.lines[0].station_ids, ("S1", "S2", "S3"))

    def test_two_lines_are_separated_by_line_id(self) -> None:
        l1 = SimpleNamespace(id="L1", name="一号线", color="#2563EB", loop=False)
        l2 = SimpleNamespace(id="L2", name="二号线", color="#D97706", loop=False)
        edges = [
            {"from": "S1", "to": "S2", "line_id": "L1"},
            {"from": "S3", "to": "S4", "line_id": "L2"},
        ]
        draw = normalise_graph(self._graph([l1, l2], edges))
        by_id = {line.id: line for line in draw.lines}
        self.assertEqual(by_id["L1"].station_ids, ("S1", "S2"))
        self.assertEqual(by_id["L2"].station_ids, ("S3", "S4"))

    def test_loop_edges_reconstruct_all_stations(self) -> None:
        line = SimpleNamespace(id="L1", name="环线", color="#2563EB", loop=True)
        edges = [
            {"from": "S1", "to": "S2", "line_id": "L1"},
            {"from": "S2", "to": "S3", "line_id": "L1"},
            {"from": "S3", "to": "S1", "line_id": "L1"},
        ]
        draw = normalise_graph(self._graph([line], edges))
        self.assertEqual(len(draw.lines[0].station_ids), 3)
        self.assertEqual(set(draw.lines[0].station_ids), {"S1", "S2", "S3"})

    def test_no_edges_and_no_stations_raises(self) -> None:
        line = SimpleNamespace(id="L1", name="一号线", color="#2563EB", loop=False)
        with self.assertRaises(ValueError):
            normalise_graph(self._graph([line], []))


class LoaderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        SMOKE.mkdir(exist_ok=True)

    def _write(self, name: str, payload: dict) -> Path:
        path = SMOKE / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_duplicate_station_id_raises(self) -> None:
        path = self._write("dup_station.json", {
            "stations": [
                {"id": "X", "name": "甲", "x": 0, "y": 0},
                {"id": "X", "name": "乙", "x": 1, "y": 1},
            ],
            "lines": [{"id": "L1", "name": "线", "stations": ["X", "X"]}],
        })
        with self.assertRaises(DataFormatError) as ctx:
            load_dataset(str(path))
        self.assertIn("重复", str(ctx.exception))

    def test_duplicate_line_id_raises(self) -> None:
        path = self._write("dup_line.json", {
            "stations": [
                {"id": "A", "name": "甲", "x": 0, "y": 0},
                {"id": "B", "name": "乙", "x": 1, "y": 0},
            ],
            "lines": [
                {"id": "L1", "name": "线一", "stations": ["A", "B"]},
                {"id": "L1", "name": "线二", "stations": ["A", "B"]},
            ],
        })
        with self.assertRaises(DataFormatError):
            load_dataset(str(path))

    def test_duplicate_station_id_in_txt_raises(self) -> None:
        path = SMOKE / "dup_station.txt"
        path.write_text(
            "CITY 测试\n"
            "STATION,X,甲,0,0\n"
            "STATION,X,乙,1,1\n"
            "LINE,L1,线,#2563EB,0,X\n",
            encoding="utf-8",
        )
        with self.assertRaises(DataFormatError):
            load_dataset(str(path))

    def test_per_line_speed_changes_ride_time(self) -> None:
        path = self._write("per_line_speed.json", {
            "meta": {"params": {"train_speed_kmh": 35.0, "dwell_minutes": 0.6}},
            "stations": [
                {"id": "A", "name": "甲", "x": 0, "y": 0},
                {"id": "B", "name": "乙", "x": 1, "y": 0},
                {"id": "C", "name": "丙", "x": 0, "y": 2},
                {"id": "D", "name": "丁", "x": 1, "y": 2},
            ],
            "lines": [
                {"id": "SLOW", "name": "慢线", "speed_kmh": 20.0,
                 "stations": ["A", "B"]},
                {"id": "FAST", "name": "快线", "speed_kmh": 60.0,
                 "stations": ["C", "D"]},
            ],
        })
        graph = load_dataset(str(path)).build_graph()
        slow_time, slow_km = graph.segment("SLOW", "A", "B")
        fast_time, fast_km = graph.segment("FAST", "C", "D")
        self.assertAlmostEqual(slow_km, fast_km)
        self.assertGreater(slow_time, fast_time)
        self.assertAlmostEqual(graph.line_speed("SLOW"), 20.0)
        self.assertAlmostEqual(graph.max_speed_kmh(), 60.0)
        # 没有写 speed_kmh 的线路仍然回退到全网默认速度
        self.assertAlmostEqual(graph.ride_time(1.0), 1.0 / 35.0 * 60 + 0.6)


class WeightTests(unittest.TestCase):
    """M1：time / distance 两种优化目标。"""

    @classmethod
    def setUpClass(cls) -> None:
        path = SMOKE / "weight_case.json"
        path.write_text(json.dumps({
            "meta": {"params": {"train_speed_kmh": 35.0, "dwell_minutes": 0.6}},
            "stations": [
                {"id": "A", "name": "甲", "x": 0, "y": 0},
                {"id": "B", "name": "乙", "x": 6, "y": 0},
                {"id": "C", "name": "丙", "x": 3, "y": 4},
                {"id": "D", "name": "丁", "x": 6, "y": 4},
            ],
            "lines": [
                # 快线绕远（10 km）但更快：11.2 min
                {"id": "L1", "name": "一号线", "speed_kmh": 60.0,
                 "stations": ["A", "B", "D"]},
                # 慢线更短（8 km）但更慢：约 14.9 min
                {"id": "L2", "name": "二号线", "speed_kmh": 35.0,
                 "stations": ["A", "C", "D"]},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        cls.graph = load_dataset(str(path)).build_graph()

    def test_time_weight_returns_time_optimal(self) -> None:
        fastest = solve(self.graph, "Dijkstra", "A", "D")
        shortest = solve(self.graph, "Dijkstra", "A", "D", weight="distance")
        self.assertEqual(fastest.weight, "time")
        self.assertEqual(shortest.weight, "distance")
        # 快线：6+4 km @60 km/h，两段各加 0.6 min 停站 = 6.6+4.6 = 11.2 min
        self.assertAlmostEqual(fastest.total_time, 11.2, places=3)
        self.assertAlmostEqual(fastest.total_distance, 10.0, places=3)
        # 慢线更短（8 km）但更慢 => “最快”与“最短里程”确实不同
        self.assertGreater(shortest.total_time, fastest.total_time)
        self.assertLess(shortest.total_distance, fastest.total_distance)

    def test_astar_matches_dijkstra_under_both_weights(self) -> None:
        for weight in ("time", "distance"):
            with self.subTest(weight=weight):
                d = solve(self.graph, "Dijkstra", "A", "D", weight=weight)
                a = solve(self.graph, "A*", "A", "D", weight=weight)
                self.assertAlmostEqual(d.total_time, a.total_time, places=6)
                self.assertAlmostEqual(d.total_distance, a.total_distance, places=6)

    def test_weight_aliases(self) -> None:
        z = solve(self.graph, "Dijkstra", "A", "D", weight="最短距离")
        self.assertEqual(z.weight, "distance")
        t = solve(self.graph, "Dijkstra", "A", "D", weight="时间")
        self.assertEqual(t.weight, "time")
        with self.assertRaises(ValueError):
            solve(self.graph, "Dijkstra", "A", "D", weight="toll")

    def test_bfs_weight_and_visited_order(self) -> None:
        bfs = solve(self.graph, "BFS", "A", "D", weight="distance")
        self.assertEqual(bfs.weight, "distance")
        self.assertTrue(bfs.found)
        self.assertGreaterEqual(len(bfs.visited_order), 2)
        self.assertEqual(bfs.visited_order[0], "A")


if __name__ == "__main__":
    unittest.main(verbosity=2)
