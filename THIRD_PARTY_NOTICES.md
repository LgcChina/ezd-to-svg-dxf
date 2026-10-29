# 第三方项目与许可证

对应工具版本：v1.2.3。以下信息依据所用 Python 发行包的 METADATA 和随包许可证核对。

## 直接依赖

| 项目 | 固定版本 | 本工具中的用途 | 许可证与版权声明 |
| --- | --- | --- | --- |
| [Meerk40t](https://github.com/meerk40t/meerk40t) | 0.9.9100 | `meerk40t.extra.ezd.EZCFile` 解析 EZD；`meerk40t.svgelements` 构建路径和矩阵 | MIT；Copyright (c) 2021 meerk40t；[原文副本](licenses/Meerk40t-MIT.txt) |
| [ezdxf](https://github.com/mozman/ezdxf) | 1.4.5 | DXF 写出、重读审计、范围核对与贝塞尔曲线离散 | MIT；Copyright (c) 2020 Manfred Moitzi；[原文副本](licenses/ezdxf-MIT.txt) |

PyPI 发行版：[meerk40t 0.9.9100](https://pypi.org/project/meerk40t/0.9.9100/)、[ezdxf 1.4.5](https://pypi.org/project/ezdxf/1.4.5/)。

Meerk40t 对应源文件位置：[EZD 解析器](https://github.com/meerk40t/meerk40t/blob/main/meerk40t/extra/ezd.py)、[svgelements](https://github.com/meerk40t/meerk40t/blob/main/meerk40t/svgelements.py)。这些链接指向上游主分支，可能随时间变化；实际使用版本以 requirements.txt 和 PyPI 发行包为准。

本仓库通过 import 使用依赖，没有复制整个解析器，也没有把 svgelements 当作额外的独立 pip 依赖。本项目的功能依赖上游工作，发布时请保留本说明及许可证原文。

Meerk40t 内置的 `svgelements.py` 还注明其路径实现源自 [regebro/svg.path](https://github.com/regebro/svg.path)，部分数学实现源自 [mathandy/svgpathtools](https://github.com/mathandy/svgpathtools)。此处保留上游来源说明；本仓库不直接安装或分发这两个项目，所用实现来自上述固定版本的 Meerk40t 包。

## pip 自动安装的间接依赖

以下是上述两个固定版本在未启用 extras 时声明的依赖。它们未全部锁定版本，pip 会按 Python 版本和平台解析，安装结果可能不同。

| 项目 | 引入方 | 主要许可证 | 项目来源 |
| --- | --- | --- | --- |
| NumPy | Meerk40t、ezdxf | 主项目 BSD-3-Clause；所装 wheel 还可能含其他许可的组件 | [numpy/numpy](https://github.com/numpy/numpy) |
| PyUSB | Meerk40t | BSD-3-Clause | [pyusb/pyusb](https://github.com/pyusb/pyusb) |
| pySerial | Meerk40t | BSD-3-Clause | [pyserial/pyserial](https://github.com/pyserial/pyserial) |
| pyparsing | ezdxf | MIT | [pyparsing/pyparsing](https://github.com/pyparsing/pyparsing) |
| typing_extensions | ezdxf | PSF-2.0；随包包含历史 Python 许可文本 | [python/typing_extensions](https://github.com/python/typing_extensions) |
| fontTools | ezdxf | MIT；部分外部组件另有声明 | [fonttools/fonttools](https://github.com/fonttools/fonttools) |

本工具只进行文件转换，不使用 USB 或串口设备；PyUSB、pySerial 是 Meerk40t 包声明的安装依赖。没有启用 Meerk40t 的 GUI/摄像头 extras 或 ezdxf 的绘图 extras。

Python 标准库按 [Python 许可证](https://docs.python.org/3/license.html) 提供；Python 解释器及 pip 本身不随仓库分发。GitHub Actions 使用官方 [actions/checkout](https://github.com/actions/checkout) 与 [actions/setup-python](https://github.com/actions/setup-python)，它们在上游各自采用 MIT，本仓库仅引用 Actions。

本仓库只分发自身脚本、文档、测试和直接依赖许可证副本。依赖由使用者通过 pip 获取，各包保留自己的许可证。若将来打包环境或分发 wheel/DLL/exe，应按实际所分发包及其捆绑组件保留完整许可，不能仅用本项目的许可证替代第三方许可证。

## 软件与图形内容

软件许可证不会改变输入 EZD、输出图案、文字、商标或其他素材的权利归属。本仓库没有附带业务图纸或厂商软件，也不声称获得 EZCAD 商标或厂商授权。
