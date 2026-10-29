"""Portable regression tests using synthetic geometry and mocked EZD objects."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ezd_to_svg", ROOT / "ezd_to_svg.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class LauncherTests(unittest.TestCase):
    def test_dependency_decline_never_installs(self):
        with patch.object(tool, "load_dependencies", side_effect=ImportError("missing")), \
             patch("builtins.input", return_value="n"), \
             patch.object(tool.subprocess, "run") as install:
            with self.assertRaisesRegex(RuntimeError, "取消"):
                tool.ensure_dependencies()
            install.assert_not_called()

    def test_dependency_confirmation_uses_current_python(self):
        with patch.object(tool, "load_dependencies", side_effect=[ImportError("missing"), None]), \
             patch("builtins.input", return_value="Y"), \
             patch.object(tool.subprocess, "run", return_value=Mock(returncode=0)) as install:
            tool.ensure_dependencies()
            self.assertEqual(install.call_args.args[0][1:], ["-m", "pip", "install", *tool.DEPENDENCIES])

    def test_install_failure_is_reported(self):
        with patch.object(tool, "load_dependencies", side_effect=ImportError("missing")), \
             patch("builtins.input", return_value="Y"), \
             patch.object(tool.subprocess, "run", return_value=Mock(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "安装失败"):
                tool.ensure_dependencies()

    def test_noninteractive_never_prompts_or_installs(self):
        with patch.object(tool, "load_dependencies", side_effect=ImportError("missing")), \
             patch("builtins.input") as prompt, patch.object(tool.subprocess, "run") as install:
            with self.assertRaisesRegex(RuntimeError, "非交互模式"):
                tool.ensure_dependencies(True)
            prompt.assert_not_called()
            install.assert_not_called()

    def test_batch_continues_after_failure_and_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            script_dir = Path(folder)
            good = script_dir / "有效文件.ezd"
            good.touch()
            missing = script_dir / "缺失文件.ezd"
            argv = ["ezd_to_svg.py", str(missing), str(good), "--non-interactive"]
            report = {"size_mm": [1, 2], "skipped_object_types": {}, "text_objects_not_emitted": [],
                      "outputs": {"report": "test_validation.json"}}
            with patch.object(tool, "SCRIPT_DIR", script_dir), \
                 patch.object(sys, "argv", argv), patch.object(tool, "ensure_dependencies"), \
                 patch.object(tool, "convert", return_value=report) as convert:
                self.assertEqual(tool.main(), 1)
                self.assertEqual(convert.call_count, 1)
                self.assertEqual(convert.call_args.args[1],
                                 script_dir / "已转换" / good.stem / f"{good.stem}_v{tool.VERSION}.svg")
                self.assertTrue((script_dir / "已转换" / missing.stem / "转换失败日志.txt").is_file())

    def test_pause_on_failure(self):
        with patch.object(tool, "open_console"), patch.object(tool, "main", side_effect=ValueError("failure")), \
             patch.object(sys, "argv", ["ezd_to_svg.py"]), patch("builtins.input", return_value="") as prompt:
            self.assertEqual(tool.run(), 1)
            prompt.assert_called_once()

class DxfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tool.load_dependencies()

    def test_bezier_flattening_and_closure_survive_roundtrip(self):
        curve = tool.VectorPath()
        curve.move((0, 0))
        curve.line((1, 0))
        curve.quad((2, 4), (4, 0))
        curve.cubic((5, -3), (7, 4), (8, 0))
        curve.closed()
        square = tool.VectorPath("M 10,10 L 12,10 L 12,12 L 10,12 Z")
        items = [{"path": curve}, {"path": square}]
        bounds = [0, min(curve.bbox()[1], square.bbox()[1]), 12, 12]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "curves.dxf"
            result = tool.export_dxf(items, target, bounds)
            self.assertEqual(result["entity_types"], {"POLYLINE": 2})
            self.assertFalse(result["fill"])
            self.assertEqual(result["flattened_curve_segments"], 2)
            doc = tool.ezdxf.readfile(target)
            lines = [edge for contour in doc.modelspace() for edge in contour.virtual_entities()]
            self.assertTrue(all(contour.is_closed for contour in doc.modelspace()))
            original = [seg for seg in curve if isinstance(seg, (tool.QuadraticBezier, tool.CubicBezier))]
            from ezdxf.math import Vec3
            def distance(point, line):
                start, end = line.dxf.start, line.dxf.end
                edge = end - start
                fraction = max(0, min(1, (point - start).dot(edge) / edge.magnitude_square))
                return (point - (start + edge * fraction)).magnitude
            for segment in original:
                for i in range(1001):
                    expected = segment.point(i / 1000)
                    self.assertLessEqual(min(distance(Vec3(expected.x, expected.y, 0), line) for line in lines),
                                         tool.DXF_CURVE_TOLERANCE_MM)
            edges = {(tuple(e.dxf.start), tuple(e.dxf.end)) for e in lines}
            self.assertIn(((8, 0, 0), (0, 0, 0)), edges)
            self.assertIn(((10, 12, 0), (10, 10, 0)), edges)
            self.assertNotIn(((0, 0, 0), (10, 10, 0)), edges)

    def test_move_never_becomes_a_line(self):
        path = tool.VectorPath("M0,0 L1,0 M100,100 L101,100")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "separate.dxf"
            result = tool.export_dxf([{"path": path}], target, [0, 0, 101, 100])
            self.assertEqual(result["entities"], 2)
            doc = tool.ezdxf.readfile(target)
            self.assertTrue(all(not entity.is_closed for entity in doc.modelspace()))
            self.assertTrue(all((e.dxf.end - e.dxf.start).magnitude == 1
                                for contour in doc.modelspace() for e in contour.virtual_entities()))

    def test_40_edges_are_one_closed_contour(self):
        import math
        path = tool.VectorPath()
        vertices = [(math.cos(i * math.tau / 40), math.sin(i * math.tau / 40)) for i in range(40)]
        path.move(vertices[0])
        path.line(*vertices[1:])
        path.closed()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "closed.dxf"
            result = tool.export_dxf([{"path": path}], target, [-1, -1, 1, 1])
            self.assertEqual(result["closed_contours"], 1)
            self.assertEqual(result["contour_segments"], 40)
            contours = list(tool.ezdxf.readfile(target).modelspace())
            self.assertEqual(len(contours), 1)
            self.assertEqual(len(contours[0].vertices), 40)
            self.assertTrue(contours[0].is_closed)

    def test_holes_remain_separate_closed_contours(self):
        path = tool.VectorPath("M0,0 L4,0 L4,4 L0,4 Z M1,1 L2,1 L2,2 L1,2 Z")
        with tempfile.TemporaryDirectory() as folder:
            result = tool.export_dxf([{"path": path}], Path(folder) / "hole.dxf", [0, 0, 4, 4])
            self.assertEqual(result["closed_contours"], 2)
            self.assertEqual(result["contour_segments"], 8)

    def test_touching_paths_are_not_merged(self):
        items = [{"path": tool.VectorPath("M0,0 L1,0")},
                 {"path": tool.VectorPath("M1,0 L2,0")}]
        with tempfile.TemporaryDirectory() as folder:
            result = tool.export_dxf(items, Path(folder) / "touching.dxf", [0, 0, 2, 0])
            self.assertEqual(result["open_contours"], 2)

    def test_zero_length_edges_removed_without_changing_geometry(self):
        path = tool.VectorPath("M0,0 L0,0 L2,0 L2,0 L2,2 L0,2 Z")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "square.dxf"
            result = tool.export_dxf([{"path": path}], target, [0, 0, 2, 2])
            self.assertEqual(result["skipped_zero_length_segments"], 2)
            self.assertEqual(result["contour_segments"], 4)
            contour, = tool.ezdxf.readfile(target).modelspace()
            self.assertEqual([(v.dxf.location.x, v.dxf.location.y) for v in contour.vertices],
                             [(0, 0), (2, 0), (2, 2), (0, 2)])

    def test_bad_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "范围"):
                tool.export_dxf([{"path": tool.VectorPath("M0,0 L1,1")}],
                                Path(folder) / "bad.dxf", [0, 0, 2, 2])

    def test_validation_failure_preserves_prior_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = directory / "sample.ezd"
            source.write_bytes("EZCADUNI".encode("utf-16-le"))
            svg = directory / "sample.svg"
            dxf = directory / "sample.dxf"
            report = directory / "sample_validation.json"
            for target in (svg, dxf, report):
                target.write_bytes(b"prior result")
            curve = type("EZCurve", (), {"points": [(1, 0, (0, 0, 1, 1))]})()
            with patch.object(tool, "EZCFile", return_value=Mock(objects=[curve])), \
                 patch.object(tool, "load_dependencies"), \
                 patch.object(tool, "export_dxf", side_effect=ValueError("audit failed")):
                with self.assertRaisesRegex(ValueError, "audit failed"):
                    tool.convert(source, svg)
            for target in (svg, dxf, report):
                self.assertEqual(target.read_bytes(), b"prior result")
            self.assertEqual(list(directory.glob(".ezd-*")), [])

    def test_output_collision_rejected(self):
        with self.assertRaisesRegex(ValueError, "路径不能相同"):
            tool.convert(Path("sample.ezd"), Path("sample.svg"), Path("sample.dxf"))

    def test_synthetic_objects_convert_to_svg_dxf_and_report(self):
        curve_type = type("EZCurve", (), {})
        outer = curve_type()
        outer.points = [(1, 1, (0, 0, 4, 0, 4, 4, 0, 4, 0, 0))]
        hole = curve_type()
        hole.points = [(1, 1, (1, 1, 2, 1, 2, 2, 1, 2, 1, 1))]
        hatch = type("EZHatch", (list,), {})([outer, hole])
        group = type("EZGroup", (list,), {})([hatch])
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = directory / "synthetic.ezd"
            # Only the header is real; the parser result is deliberately mocked.
            source.write_bytes("EZCADUNI".encode("utf-16-le"))
            target = directory / "result.svg"
            with patch.object(tool, "EZCFile", return_value=Mock(objects=[group])), \
                 patch.object(tool, "load_dependencies"):
                result = tool.convert(source, target)
            self.assertEqual(result["version"], tool.VERSION)
            self.assertEqual(result["size_mm"], [4, 4])
            self.assertEqual(result["skipped_object_types"], {})
            self.assertEqual(result["dxf"]["closed_contours"], 2)
            self.assertTrue(result["dxf"]["contour_vertices_verified"])
            root = ET.parse(target).getroot()
            self.assertEqual(root.attrib["viewBox"], "0.000000000 -4.000000000 4.000000000 4.000000000")
            ns = {"s": tool.SVG_NS}
            path, = root.findall(".//s:path", ns)
            self.assertEqual(path.attrib["fill"], "black")
            self.assertEqual(path.attrib["fill-rule"], "evenodd")
            self.assertEqual(root.find("s:g", ns).attrib["transform"], "scale(1,-1)")
            stored = json.loads(target.with_name("result_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(stored, result)
            self.assertEqual(len(stored["input_sha256"]), 64)

    def test_unsupported_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "unknown.ezd"
            source.write_bytes(b"not an EZCAD2 file")
            with self.assertRaisesRegex(ValueError, "EZCADUNI"):
                tool.convert(source, Path(folder) / "result.svg")


if __name__ == "__main__":
    unittest.main()
