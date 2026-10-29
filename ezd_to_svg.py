#!/usr/bin/env python3
"""Convert EZCAD2 EZD vector data to SVG and DXF.

Version: 1.2.3
This tool reads vector objects stored in an EZD file. It does not trace the preview bitmap.
Dependencies: meerk40t, ezdxf (installation requires confirmation).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

VERSION = "1.2.3"
DXF_CURVE_TOLERANCE_MM = 0.001
DEPENDENCIES = ("meerk40t==0.9.9100", "ezdxf==1.4.5")
SCRIPT_DIR = Path(__file__).resolve().parent
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def open_console():
    """Restore a console when Windows associates .py with pythonw.exe."""
    if os.name != "nt":
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    needs_console = Path(sys.executable).name.lower() == "pythonw.exe" or any(
        stream is None for stream in (sys.stdin, sys.stdout, sys.stderr)
    )
    if not kernel.GetConsoleWindow() and needs_console:
        if not kernel.AllocConsole():
            raise RuntimeError("无法创建控制台，请使用配套的 .bat 启动器运行。")
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        kernel.SetConsoleCP(65001)
        kernel.SetConsoleOutputCP(65001)
    kernel.SetConsoleTitleW(f"EZD to SVG + DXF v{VERSION}")


def load_dependencies():
    global EZCFile, VectorPath, Matrix, Move, Line, Close, CubicBezier, QuadraticBezier, ezdxf
    from meerk40t.extra.ezd import EZCFile
    from meerk40t.svgelements import (
        Path as VectorPath, Matrix, Move, Line, Close, CubicBezier, QuadraticBezier,
    )
    import ezdxf


def ensure_dependencies(non_interactive=False):
    try:
        load_dependencies()
        return
    except ImportError as exc:
        print(f"缺少解析依赖：{exc}", flush=True)
    packages = " ".join(DEPENDENCIES)
    print(f"需要安装或补齐：{packages} 及其依赖。安装需要联网，使用当前 Python 环境。")
    if non_interactive:
        raise RuntimeError(f"非交互模式不会安装依赖。请运行：python -m pip install {packages}")
    answer = input("是否现在自动安装？输入 Y 确认，其他输入取消 [y/N]：").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("已取消安装，没有执行转换。")
    interpreter = Path(sys.executable)
    if interpreter.name.lower() == "pythonw.exe":
        interpreter = interpreter.with_name("python.exe")
    print("正在安装，请等待；下方会显示 pip 安装进度。", flush=True)
    result = subprocess.run(
        [str(interpreter), "-m", "pip", "install", *DEPENDENCIES],
        stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
    )
    if result.returncode:
        raise RuntimeError(f"依赖安装失败（退出码 {result.returncode}），请检查上方 pip 信息。")
    import importlib
    importlib.invalidate_caches()
    load_dependencies()
    print("依赖安装完成。", flush=True)


def path_for_curve(obj):
    path = VectorPath()
    last = None
    for curve_type, closed, coords in obj.points:
        points = [complex(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
        if not points:
            continue
        if last != points[0]:
            path.move(points[0])
        if curve_type == 1:
            path.line(*points[1:])
        elif curve_type == 2:
            path.quad(*points[1:])
        elif curve_type == 3:
            path.cubic(*points[1:])
        else:
            raise ValueError(f"unsupported EZCAD curve type: {curve_type}")
        last = points[-1]
    if obj.points and obj.points[-1][1]:
        path.closed()
    return path


def path_for_rect(obj):
    x0, y0 = obj.corner_upper_left
    x1, y1 = obj.corner_bottom_right
    path = VectorPath()
    path.move((x0, y0))
    path.line((x1, y0), (x1, y1), (x0, y1), (x0, y0))
    path.closed()
    matrix = obj.matrix
    path *= Matrix(matrix[0], matrix[1], matrix[3], matrix[4], matrix[6], matrix[7])
    return abs(path)


def export_dxf(paths, output_path: Path, expected_bounds) -> dict:
    from ezdxf import bbox
    from ezdxf.math import Bezier3P, Bezier4P, Vec3

    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    doc.layers.new("OUTLINES", dxfattribs={"color": 7})
    model = doc.modelspace()
    attrs = {"layer": "OUTLINES"}
    segment_count = 0
    zero_length_count = 0
    curve_count = 0
    contours = []
    points = []

    def flush_contour():
        nonlocal points
        if len(points) >= 2:
            closed = points[0] == points[-1]
            vertices = points[:-1] if closed else points
            model.add_polyline2d(vertices, close=closed, dxfattribs=attrs)
            contours.append((list(vertices), closed))
        points = []

    def add_edge(start, end):
        nonlocal segment_count, zero_length_count
        start, end = tuple(start)[:2], tuple(end)[:2]
        if start == end:
            zero_length_count += 1
            return
        if points and points[-1] != start:
            flush_contour()
        if not points:
            points.append(start)
        points.append(end)
        segment_count += 1

    # Classic POLYLINE keeps each contour editable as one entity. Never join
    # across a Move, a Close, an input path boundary, or a discontinuous edge.
    for item in paths:
        for segment in item["path"]:
            if isinstance(segment, Move):
                flush_contour()
                continue
            if isinstance(segment, (Line, Close)):
                add_edge(tuple(segment.start), tuple(segment.end))
                if isinstance(segment, Close):
                    flush_contour()
            elif isinstance(segment, (CubicBezier, QuadraticBezier)):
                curve_count += 1
                if isinstance(segment, CubicBezier):
                    controls = [segment.start, segment.control1, segment.control2, segment.end]
                    curve = Bezier4P([Vec3(p.x, p.y, 0) for p in controls])
                else:
                    controls = [segment.start, segment.control, segment.end]
                    curve = Bezier3P([Vec3(p.x, p.y, 0) for p in controls])
                vertices = iter(curve.flattening(DXF_CURVE_TOLERANCE_MM))
                start = next(vertices)
                for end in vertices:
                    add_edge(tuple(start), tuple(end))
                    start = end
            else:
                raise ValueError(f"无法导出 DXF 曲线：{type(segment).__name__}")
        flush_contour()
    doc.saveas(output_path)
    reopened = ezdxf.readfile(output_path)
    auditor = reopened.audit()
    if auditor.has_errors or auditor.has_fixes:
        raise ValueError(f"DXF 审计未通过：{len(auditor.errors)} 个错误，{len(auditor.fixes)} 个修复")
    if reopened.units != ezdxf.units.MM:
        raise ValueError("DXF 单位校验未通过")
    if len(reopened.modelspace()) != len(contours) or any(
        entity.dxftype() != "POLYLINE" or not entity.is_2d_polyline
        for entity in reopened.modelspace()
    ):
        raise ValueError("DXF 轮廓校验未通过：每个轮廓应为一个二维 POLYLINE。")
    for entity, (vertices, closed) in zip(reopened.modelspace(), contours):
        restored = [(vertex.dxf.location.x, vertex.dxf.location.y) for vertex in entity.vertices]
        if restored != vertices or bool(entity.is_closed) != closed:
            raise ValueError("DXF 轮廓校验未通过：顶点或闭合状态发生变化。")
    extents = bbox.extents(reopened.modelspace())
    if not extents.has_data:
        raise ValueError("DXF 没有可校验的图形")
    actual = [extents.extmin.x, extents.extmin.y, extents.extmax.x, extents.extmax.y]
    tolerance = DXF_CURVE_TOLERANCE_MM + 1e-5 if curve_count else 1e-5
    if any(abs(a - b) > tolerance for a, b in zip(actual, expected_bounds)):
        raise ValueError(f"DXF 范围与原曲线不一致：{actual} / {expected_bounds}")
    return {
        "format": "R2010", "units": "mm", "entities": len(reopened.modelspace()),
        "mode": "classic_polyline_contours_no_fill", "fill": False,
        "contours": len(contours), "contour_segments": segment_count,
        "closed_contours": sum(closed for _, closed in contours),
        "open_contours": sum(not closed for _, closed in contours),
        "contour_vertices_verified": True,
        "curve_tolerance_mm": DXF_CURVE_TOLERANCE_MM,
        "flattened_curve_segments": curve_count,
        "skipped_zero_length_segments": zero_length_count,
        "entity_types": dict(Counter(entity.dxftype() for entity in reopened.modelspace())),
        "audit_errors": len(auditor.errors), "audit_fixes": len(auditor.fixes),
        "bounds_mm": actual, "bounds_verified": True, "bounds_tolerance_mm": tolerance,
    }


def convert(input_path: Path, output_path: Path, report_path: Path | None = None) -> dict:
    """Write SVG, a sibling DXF, and a JSON report after validation."""
    load_dependencies()
    if output_path.suffix.lower() != ".svg":
        raise ValueError("--output 必须使用 .svg 扩展名；同名 DXF 会自动生成。")
    dxf_path = output_path.with_suffix(".dxf")
    if report_path is None:
        report_path = output_path.with_name(output_path.stem + "_validation.json")
    targets = [input_path.resolve(), output_path.resolve(), dxf_path.resolve(), report_path.resolve()]
    if len(set(targets)) != len(targets):
        raise ValueError("输入、SVG、DXF 和校验记录的路径不能相同。")
    with input_path.open("rb") as stream:
        if stream.read(16) != "EZCADUNI".encode("utf-16-le"):
            raise ValueError("文件头不是 EZCADUNI，暂不支持此 EZD 格式。")
    print("  [1/4] 正在解析 EZD，较大的文件可能需要等待...", flush=True)
    with input_path.open("rb") as stream:
        ez = EZCFile(stream)

    print("  [2/4] 正在提取曲线和填充轮廓...", flush=True)
    paths: list[dict] = []
    counts = Counter()
    skipped = Counter()
    text_objects = []

    def visit(obj, fill_index: int | None = None):
        name = type(obj).__name__
        counts[name] += 1
        if name == "EZText":
            text_objects.append({"text": obj.text, "font": obj.font, "position": list(obj.position)})
            # EZCAD often stores the text's actual outline in a sibling EZHatch.
            # Do not emit SVG <text>; its appearance would depend on installed fonts.
            return
        if name == "EZHatch":
            fill_index = len(paths)
            paths.append({"path": VectorPath(), "fill": True, "label": "hatch"})
        if name == "EZCurve":
            vector_path = path_for_curve(obj)
            if fill_index is None:
                paths.append({"path": vector_path, "fill": False, "label": name})
            else:
                paths[fill_index]["path"].extend(vector_path)
        elif name == "EZRect":
            vector_path = path_for_rect(obj)
            if fill_index is None:
                paths.append({"path": vector_path, "fill": False, "label": name})
            else:
                paths[fill_index]["path"].extend(vector_path)
        elif isinstance(obj, list):
            for child in obj:
                visit(child, fill_index)
        elif name not in {"EZGroup", "EZVectorFile", "EZCombine", "EZSpiral"}:
            skipped[name] += 1

    for obj in ez.objects:
        visit(obj)

    nonempty = [item["path"].bbox() for item in paths if len(item["path"])]
    if not nonempty:
        raise ValueError("没有找到可导出的 EZCurve/EZRect 矢量对象")
    xmin = min(box[0] for box in nonempty)
    ymin = min(box[1] for box in nonempty)
    xmax = max(box[2] for box in nonempty)
    ymax = max(box[3] for box in nonempty)
    width, height = xmax - xmin, ymax - ymin

    root = ET.Element(f"{{{SVG_NS}}}svg", {
        "version": "1.1", "width": f"{width:.9f}mm", "height": f"{height:.9f}mm",
        "viewBox": f"{xmin:.9f} {-ymax:.9f} {width:.9f} {height:.9f}",
    })
    ET.SubElement(root, f"{{{SVG_NS}}}title").text = f"Recovered from EZD v{VERSION}"
    group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"transform": "scale(1,-1)"})
    for index, item in enumerate(paths):
        ET.SubElement(group, f"{{{SVG_NS}}}path", {
            "id": f"object-{index}", "d": item["path"].d(),
            "fill": "black" if item["fill"] else "none",
            "fill-rule": "evenodd", "stroke": "none" if item["fill"] else "black",
            "stroke-width": "0.04",
        })
    report = {
        "version": VERSION,
        "input": str(input_path.resolve()),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "output": str(output_path.resolve()),
        "outputs": {"svg": str(output_path.resolve()), "dxf": str(dxf_path.resolve()),
                    "report": str(report_path.resolve())},
        "objects": dict(counts),
        "svg_paths": len(paths),
        "bounds_mm": [xmin, ymin, xmax, ymax],
        "size_mm": [width, height],
        "text_objects_not_emitted": text_objects,
        "skipped_object_types": dict(skipped),
        "notes": [
            "Coordinates are extracted from EZD vector data; the preview bitmap is not traced.",
            "EZCAD text is not emitted as SVG text because its appearance depends on fonts; use saved outline/hatch geometry when present.",
            "Laser power, speed, frequency, pen parameters, and hatch processing settings are not SVG geometry.",
            "DXF R2010 uses one classic 2D POLYLINE per contour, without fill or links between contours; Bezier curves are flattened at 0.001 mm tolerance.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Validate staged files before replacing any previous conversion results.
    with tempfile.TemporaryDirectory(prefix=".ezd-", dir=output_path.parent) as staging:
        stage = Path(staging)
        print("  [3/4] 正在生成 SVG、DXF 并检查 DXF 尺寸和完整性...", flush=True)
        svg_temp = stage / "result.svg"
        dxf_temp = stage / "result.dxf"
        report_temp = stage / "validation.json"
        ET.ElementTree(root).write(svg_temp, encoding="utf-8", xml_declaration=True)
        ET.parse(svg_temp)
        report["dxf"] = export_dxf(paths, dxf_temp, [xmin, ymin, xmax, ymax])
        report_temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  [4/4] 校验通过，正在保存 SVG、DXF 和校验记录...", flush=True)
        # Stage the report in its destination directory, which may be on another drive.
        with tempfile.NamedTemporaryFile(dir=report_path.parent, delete=False) as stream:
            staged_report = Path(stream.name)
            stream.write(report_temp.read_bytes())
        try:
            svg_temp.replace(output_path)
            dxf_temp.replace(dxf_path)
            staged_report.replace(report_path)
        finally:
            staged_report.unlink(missing_ok=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="将 EZCAD2 .ezd 中的矢量对象同时导出为 SVG 和 DXF")
    parser.add_argument("input", type=Path, nargs="*", help="输入一个或多个 .ezd 文件，可拖入脚本")
    parser.add_argument("-o", "--output", type=Path, help="指定 .svg 路径，同名 .dxf 自动生成（仅单文件）")
    parser.add_argument("--report", type=Path, help="转换记录 JSON 路径")
    parser.add_argument("--no-pause", action="store_true", help="结束时不等待回车，供终端和自动化调用")
    parser.add_argument("--non-interactive", action="store_true", help="不询问路径、不安装依赖、不等待回车")
    args = parser.parse_args()
    print(f"EZD 转 SVG + DXF v{VERSION}\nPython：{sys.executable}", flush=True)
    if not args.input:
        if args.non_interactive:
            parser.error("请提供 EZD 文件路径")
        value = input("请将一个 EZD 文件拖入此窗口，再按回车：").strip().strip('"')
        if not value:
            raise ValueError("未提供 EZD 文件。")
        args.input = [Path(value)]
    if len(args.input) != 1 and (args.output or args.report):
        parser.error("--output 和 --report 只能用于单文件转换")
    ensure_dependencies(args.non_interactive)
    failed = 0
    for index, input_path in enumerate(args.input, 1):
        output_dir = SCRIPT_DIR / "已转换" / input_path.stem
        output = args.output or output_dir / f"{input_path.stem}_v{VERSION}.svg"
        print(f"\n[{index}/{len(args.input)}] {input_path}\nSVG：{output.resolve()}"
              f"\nDXF：{output.with_suffix('.dxf').resolve()}", flush=True)
        started = time.monotonic()
        try:
            if not input_path.is_file():
                raise FileNotFoundError(f"文件不存在：{input_path}")
            if input_path.suffix.lower() != ".ezd":
                raise ValueError("仅接受 .ezd 文件。")
            report = convert(input_path, output, args.report)
            print(f"转换完成，耗时 {time.monotonic()-started:.1f} 秒；"
                  f"范围 {report['size_mm'][0]:.3f} x {report['size_mm'][1]:.3f} mm。", flush=True)
            print(f"校验记录：{report['outputs']['report']}")
            print("DXF 为轮廓版；使用时请重新设置填充和加工参数。")
            if report["skipped_object_types"]:
                print(f"注意：有未转换对象 {report['skipped_object_types']}，请对照原图检查。")
            if report["text_objects_not_emitted"]:
                print("注意：存在文字对象，已保存的曲线会导出；请核对文字/二维码是否完整。")
        except Exception as exc:
            failed += 1
            print(f"转换失败：{exc}", flush=True)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                error_path = output_dir / "转换失败日志.txt"
                error_path.write_text(
                    f"EZD to SVG + DXF v{VERSION}\n输入：{input_path.resolve()}\n{traceback.format_exc()}",
                    encoding="utf-8",
                )
                print(f"失败日志：{error_path}")
            except OSError as log_exc:
                print(f"日志无法保存：{log_exc}")
    print(f"\n处理结束：成功 {len(args.input)-failed}，失败 {failed}。", flush=True)
    return 1 if failed else 0


def run() -> int:
    try:
        open_console()
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        return main()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        return 1
    except Exception as exc:
        print(f"运行失败：{exc}", flush=True)
        return 1
    finally:
        if not any(flag in sys.argv[1:] for flag in ("--no-pause", "--non-interactive")):
            try:
                input("\n按回车关闭窗口...")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(run())
