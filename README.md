# EZD 还原 SVG / DXF

有个镭雕文件，由于设计人员丢失了原图稿例如ai或者pdf，现在想从镭雕电脑从ezd重新输出回来再次修改编辑，不想从头做
于是让ai去试试找方法，然后我得到了这个，至少转完后，我这里看着还好，不保证能适配所有情况

工具从 EZCAD2 的 `.ezd` 文件提取已保存的矢量轮廓，生成 **SVG、空心轮廓 DXF 和 JSON 校验记录**。直接读取矢量数据，不描摹预览位图，也不需要安装或运行 EZCAD。

当前版本：**v1.2.3**。提供 Python 脚本和bat，其实一样，不提供 exe，懒得打包。

## 快速使用（Windows）

1. 安装 [Python](https://www.python.org/downloads/windows/) **3.10 或更高版本**，安装时勾选将 Python 加入 PATH。
2. 下载本仓库 ZIP 并解压到可写目录，或通过 Git 克隆仓库。不要在 ZIP 内直接运行。
3. 将一个 `.ezd` 文件拖到 **`ezd_to_svg.bat`** 上或者打开ezd_to_svg.py，应该也会显示提示叫你拖入ezd文件然后按回车。
4. 也可双击 `.bat`，将一个文件拖入控制台后按回车。直接拖到 `.py` 取决于 Windows 文件关联；若打开编辑器或无反应，请用 `.bat`。
5. 首次运行缺少依赖时会提示，输入 **Y** 并按回车确认安装。pip 安装需要联网，使用启动脚本的当前 Python 环境。
6. 控制台显示进度和结果，结束后窗口保留。文件保存在脚本旁的 `已转换` 文件夹。


```text
工具目录/
├── ezd_to_svg.py
├── ezd_to_svg.bat
└── 已转换/
    └── sample/
        ├── sample_v1.2.3.svg
        ├── sample_v1.2.3.dxf
        └── sample_v1.2.3_validation.json
```

原始 EZD 不会被修改。同版本重复转换会覆盖对应结果；

## 命令行，这部分我看不懂，就不介绍了

在仓库根目录打开终端，可预装依赖：

```powershell
python -m pip install -r requirements.txt
python ezd_to_svg.py "D:\图纸\sample.ezd"
```

自动化和批量转换：

```powershell
python ezd_to_svg.py "D:\图纸\a.ezd" "D:\图纸\b.ezd" --non-interactive
```

`--non-interactive` 禁止输入路径、安装确认和结束等待，缺少依赖则失败退出。`--no-pause` 仅取消结束等待，仍可能询问路径或安装。

自定义输出（仅限单文件，自动生成同名 DXF）：

```powershell
python ezd_to_svg.py "D:\图纸\sample.ezd" --output "D:\结果\sample.svg" --report "D:\结果\check.json" --non-interactive
```

可选：先用 `python -m venv .venv` 创建独立环境，再用 `.\.venv\Scripts\python.exe` 执行上述 pip 和转换命令。BAT 优先使用 PATH 中的 `python`，找不到时使用 `py -3`；独立环境需先激活，或直接调用其解释器。

## 支持范围与输出区别

| 内容 | 处理方式 |
| --- | --- |
| 输入 | EZCAD2 `EZCADUNI` 格式；不保证兼容所有 EZD 版本 |
| 曲线、直线、矩形 | 从已保存坐标恢复；递归访问组合与填充对象中的矢量子对象 |
| SVG | 毫米单位，保留直线及二次/三次贝塞尔曲线；填充轮廓使用 evenodd 保留孔洞 |
| DXF | R2010，毫米单位，`OUTLINES` 图层；每个连续轮廓一个传统二维 `POLYLINE`，无填充 |
| DXF 曲线 | 按 `0.001 mm` 容差离散为同一轮廓中的顶点；SVG 仍保留曲线 |
| 封闭图案 | 例如 40 条边保存为一个闭合轮廓；内孔另为轮廓，开放路径保持开放 |
| 文字、二维码 | 只提取文件中已有的轮廓；不会生成字体文字或依据文字重新生成二维码 |
| 位图、其他对象 | 不做位图描摹；尚未支持的对象可能跳过，不能保证整图完整恢复 |
| 镭雕参数 | 不转换功率、速度、频率、笔号和填充加工参数 |

**转换成功和 DXF 审计通过，不代表图案完整或所有软件导入兼容。** 应将结果与 EZCAD 原图对照，检查文字、二维码、孔洞和尺寸，重新设置填充及加工参数。当前传统 POLYLINE 方案已通过程序校验，仍需在目标 EZCAD 空白文档中复核显示及单轮廓选择效果。

`*_validation.json` 记录输入 SHA-256、对象数量、未输出文字、跳过类型、尺寸及 DXF 顶点/闭合/单位/审计结果。底层解析器也可能忽略未知内容，因此跳过列表为空不证明完整。详见 [实现与维护说明](docs/IMPLEMENTATION.md)。

## 常见问题

- **窗口不出现或一闪而过**：使用 `.bat`；仍有问题时在终端执行 `python --version`，确认解释器为 3.10+。BAT 不会自动挑选最高版本。
- **安装失败**：查看窗口中的 pip 错误，确认网络和 Python 环境。可在终端手动执行 `python -m pip install -r requirements.txt`。取消安装不会开始转换。
- **DXF 看不到图案**：图形保留原坐标，可能位于负坐标区，在 CAD 中使用“缩放到全部/范围”。
- **看到旧结果**：转换失败时此前的结果可能仍在，请核对控制台、本次文件时间和版本。失败日志位于脚本目录的 `已转换/文件名/转换失败日志.txt`，即使指定了输出路径也是如此。
- **一个文件失败后**：批量任务继续处理其余文件；全部成功返回退出码 0，有失败返回 1。

## 项目结构

```text
.
├── ezd_to_svg.py             # 转换、校验、依赖确认与控制台入口
├── ezd_to_svg.bat            # Windows 拖放启动器
├── requirements.txt         # 固定直接依赖版本
├── README.md                # 使用说明
├── CHANGELOG.md             # 版本与修改记录
├── THIRD_PARTY_NOTICES.md    # 引用项目、用途与许可证
├── LICENSE                  # 本项目 MIT 许可证
├── docs/IMPLEMENTATION.md   # 原理、支持边界及后续维护步骤
├── licenses/               # 两个直接依赖的 MIT 许可证原文
├── tests/test_converter.py # 合成数据测试，不包含业务图纸
└── .github/workflows/tests.yml # GitHub Actions 测试
```

## 开发与验证

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

测试包括安装确认/取消/失败、批量错误处理、闭合与分离轮廓、曲线离散误差、SVG/DXF/JSON 输出和校验失败保留旧文件。测试中的解析对象为合成数据，不能代替真实 EZD 的兼容性测试。CI 配置覆盖 Windows / Ubuntu、Python 3.10 / 3.12；具体运行结果以 GitHub Actions 为准。

## 引用与许可证

主要依赖 [Meerk40t](https://github.com/meerk40t/meerk40t) 的 EZD 解析器与 `svgelements` 路径类，以及 [ezdxf](https://github.com/mozman/ezdxf) 的 DXF 写出、曲线离散和审计功能。均通过 pip 安装，本仓库不附带这些项目的源码或二进制文件。

详细来源、间接依赖和许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本工具与 EZCAD/Jcz 无隶属关系，不包含 EZCAD、演示版、SDK 或厂商 DLL，运行时也不调用它们。

本项目脚本、文档及测试按 [MIT 许可证](LICENSE) 发布，允许使用、修改和商用，分发时须保留版权和许可声明。第三方项目各自保留原许可证；输入和输出图形的权利不因软件许可证而改变。

# 免责声明

本工具由 AI 辅助制作/生成，仅用于学习、交流与参考目的，不构成任何专业建议或保证。

1. **内容准确性**：本工具的输出内容可能存在错误、遗漏或不准确之处，使用者应自行核实。
2. **使用风险**：使用者应自行评估并承担使用本工具及相关内容所产生的风险。
3. **责任限制**：作者/开发者不对因使用或依赖本工具而导致的任何直接或间接损失承担责任。
4. **合规义务**：使用者应自行确保使用行为符合所在地法律法规、平台规则及第三方权利要求。
5. **无担保**：本工具按“现状”提供，不附带任何明示或默示的担保，包括但不限于适用性、稳定性与安全性保证。

如继续使用本工具，即视为您已阅读并理解本免责声明。
