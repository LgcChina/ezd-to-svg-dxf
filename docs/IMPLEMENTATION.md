# 实现与维护说明

版本：v1.2.3；更新日期：2026-10-29。使用方法见 [README](../README.md)，修改前复核 [CHANGELOG](../CHANGELOG.md)。

## 1. 核心原理

EZD 是包含矢量对象的二进制工程文件。本工具直接读取这些对象，并非截图描摹，也不操作 EZCAD 界面。

1. 检查输入头 16 字节是否为 `EZCADUNI` 的 UTF-16-LE 编码。
2. 交由 Meerk40t 的 `EZCFile` 读取偏移、解压 Huffman 数据并解析对象。
3. 递归遍历对象树。将 `EZCurve` 的直线/二次/三次贝塞尔坐标和 `EZRect` 的矩形及矩阵转换为 `svgelements.Path`。组合等列表容器中的子对象会被访问。
4. `EZHatch` 的已有轮廓聚合为填充路径，SVG 用 evenodd 保留孔洞。
5. 计算矢量范围；SVG 以毫米写入尺寸，通过 `scale(1,-1)` 将 EZCAD 的 Y 轴方向转换到 SVG 坐标。
6. 同一批路径写出 DXF：保留原始坐标及毫米单位，采用 R2010 格式和 `OUTLINES` 图层。
7. 先在临时目录生成并校验结果，通过后依次替换 SVG、DXF、JSON。

关键代码：`path_for_curve()`、`path_for_rect()`、`export_dxf()`、`convert()`。命令行、安装确认与批量逻辑位于 `main()`、`ensure_dependencies()` 和 `run()`。

## 2. DXF 连续轮廓

采用传统二维 `POLYLINE`，DXF 内为 `POLYLINE/VERTEX/SEQEND` 编码。每个连续轮廓是一个实体，40 条连续边的闭合图案是一个闭合对象。外边界与内孔分别为轮廓，不跨轮廓强行合并。

- Move 不生成线并分隔轮廓；Close 只关闭当前轮廓。
- 不连续边和输入路径边界分隔轮廓，即使两个独立路径端点相接也不合并。
- 首尾坐标完全相同的轮廓保存为闭合对象，其余保持开放。仅删除坐标完全相同的零长度边，不进行带容差的焊接。
- 二次/三次曲线通过 ezdxf `Bezier3P` / `Bezier4P` 自适应离散，容差 `0.001 mm`。控制点先转为 `Vec3`。
- 不写 HATCH、填充扫描线、SOLID 或跨轮廓连接线；不用 LWPOLYLINE。

早期 LWPOLYLINE 方案通用审计通过，但用户导入 EZCAD 看到横线；独立 LINE 方案消除了横线却拆散轮廓。当前传统 POLYLINE 方案用于兼顾轮廓整体性，程序校验已通过，实际 EZCAD 版本兼容性仍需用户在空白文档中验证。不能将通用 DXF 审计当作目标软件兼容性保证。

## 3. 校验与输出行为

SVG 会重新做 XML 解析。DXF 保存后重读，要求审计错误数与修复数均为零，单位为毫米，每个实体为二维 POLYLINE；逐轮廓核对顶点顺序、坐标和闭合状态。纯直线的范围误差阈值为 `0.00001 mm`，有离散曲线时为 `0.00101 mm`。

JSON 主要字段：

| 字段 | 含义 |
| --- | --- |
| `version`、`input_sha256` | 本次工具版本与输入文件指纹 |
| `outputs` | SVG / DXF / 记录的绝对路径 |
| `objects`、`svg_paths` | 解析对象和 SVG 路径数量 |
| `bounds_mm`、`size_mm` | 恢复出的几何范围与尺寸，不代表材料外形 |
| `skipped_object_types` | 脚本识别到但没有转换的对象类型 |
| `text_objects_not_emitted` | 未作为字体文字输出的内容、字体与位置 |
| `dxf.mode`、`dxf.fill` | `classic_polyline_contours_no_fill`、`false` |
| `dxf.contours`、`closed_contours`、`open_contours` | 总轮廓数、闭合数、开放数（后两项也在 `dxf` 内） |
| `dxf.contour_segments` | 轮廓有效边数 |
| `dxf.contour_vertices_verified` | 完整顶点及闭合状态是否通过核对 |
| `dxf.bounds_verified`、`audit_errors`、`audit_fixes` | 范围、审计结果（后两项也在 `dxf` 内） |
| `dxf.curve_tolerance_mm` | 曲线离散容差 |

校验失败时不替换本次临时结果，已有结果保留。三个最终文件的替换依次执行，**不是三个文件共同的原子事务**：如保存阶段断电或文件占用，可能只有部分文件更新，需按控制台结果重新转换。批量失败会继续其他文件，返回非零退出码。

默认输出固定为 `脚本目录/已转换/输入文件名/输入文件名_v版本.*`，与当前命令目录和输入目录无关。同名输入可能覆盖。自定义 `--output` 必须以 `.svg` 结尾，DXF 自动同名；可独立指定 JSON 路径。

## 4. 支持边界

- 仅处理已保存且上游解析器能理解的 EZCAD2 数据，不保证 EZCAD3 或所有 EZD 变体。
- 直接导出的图形类型为 EZCurve、EZRect；容器子对象可以递归提取，但不表示所有 EZCAD 对象都已实现。
- 不把 EZText 写成 SVG `<text>`。文件已有文字/二维码轮廓时可提取；只有文字信息时，JSON 记录文字，不会自动转轮廓。缺失字体或 QR 轮廓不能靠本脚本补齐。
- 不输出位图、不做位图描摹，不保留颜色、加工顺序和激光加工参数。
- `skipped_object_types` 为空也不能证明完整：上游解析器可能忽略或部分恢复不支持的内容。输出存在、XML 可解析、DXF 审计通过，均不等于图案与原文件完全一致。

首次处理新类型的文件，应与原图对照，检查文字/二维码、孔洞、闭合轮廓、尺寸和目标软件显示。

## 5. 后续需求处理步骤

1. 先读 README、本文件和 CHANGELOG，核对 `VERSION` 与依赖固定版本。
2. 复现用户问题，确认当前使用的输出文件版本。为保护用户工作，需打开 EZCAD 验证时使用空白文档或副本。
3. 根据问题定位解析、坐标转换、SVG、DXF 轮廓或启动流程，避免同时改动无关模块。
4. 每次修改递增脚本版本及模块头版本，同步 README 输出示例、文档版本、CHANGELOG；保持 `DEPENDENCIES` 与 requirements.txt 一致。
5. 在项目根目录运行 `python -m unittest discover -s tests -v`。新增对象或几何规则时补充相应合成用例。
6. 算法修改后用有授权的真实 EZD 在仓库外做回归，比较 SVG 几何与 DXF 轮廓、尺寸、闭合状态；测试不能只检查文件存在。涉及 EZCAD 兼容时仍需在目标软件验证。
7. 在 CHANGELOG 记录行为变化、验证结果和未验证事项。不要提交私有图纸、转换结果、含本机路径或文字内容的记录和日志。

自动测试中使用合成解析对象，并未内置完整的 EZD 二进制样例；这可以测试转换流水线，无法证明上游解压和解析对任意文件兼容。GitHub Actions 配置不等于其已在 GitHub 成功运行。

## 6. Python 调用

```python
from pathlib import Path
from ezd_to_svg import convert

report = convert(Path("sample.ezd"), Path("result.svg"))
print(report["size_mm"])
```

`convert()` 同时生成同名 DXF 和默认 JSON；可用第三个参数指定 JSON 路径。该函数直接加载依赖，缺少时抛异常，不询问安装。依赖安装、批量组织及结束等待属于 CLI 层。函数需要 pathlib.Path 参数。
