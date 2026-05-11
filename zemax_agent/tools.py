"""Zemax 工具定义与实现 — 供 AI Agent 调用."""

import json
import traceback

from zemax_connection import ZemaxConnection
from logger import logger

# ---------------------------------------------------------------------------
#  OpenAI function-calling 工具模式定义
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": (
                "获取当前光学系统概览：所有表面（编号/类型/曲率半径/厚度/材料/半口径/圆锥系数）、"
                "系统光圈、视场点、波长配置"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_surface",
            "description": "在指定位置插入一个新的标准表面",
            "parameters": {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "integer",
                        "description": "插入位置的表面编号 (0=物面后, N=像面前)",
                    }
                },
                "required": ["position"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_surface",
            "description": (
                "编辑指定表面的属性。只需提供要修改的参数，未提供的保持不变。"
                "radius=1e18 表示平面 (Infinity)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "surface_number": {
                        "type": "integer",
                        "description": "表面编号 (0=物面, 最后一个=像面)",
                    },
                    "radius": {
                        "type": "number",
                        "description": "曲率半径 (mm)，正值凸面朝向物方",
                    },
                    "thickness": {
                        "type": "number",
                        "description": "到下一面的距离 (mm)",
                    },
                    "material": {
                        "type": "string",
                        "description": "玻璃材料名称，如 BK7, N-BK7, SF2, MIRROR 等",
                    },
                    "semi_diameter": {
                        "type": "number",
                        "description": "半口径 (mm)",
                    },
                    "conic": {
                        "type": "number",
                        "description": "圆锥系数 (0=球面, -1=抛物面)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "表面注释",
                    },
                    "is_stop": {
                        "type": "boolean",
                        "description": "是否设为光阑面",
                    },
                },
                "required": ["surface_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_surface",
            "description": "删除指定编号的表面（不能删除物面和像面）",
            "parameters": {
                "type": "object",
                "properties": {
                    "surface_number": {
                        "type": "integer",
                        "description": "要删除的表面编号",
                    }
                },
                "required": ["surface_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_aperture",
            "description": "设置系统光圈类型和数值",
            "parameters": {
                "type": "object",
                "properties": {
                    "aperture_type": {
                        "type": "string",
                        "enum": [
                            "EntrancePupilDiameter",
                            "ImageSpaceFNumber",
                            "ObjectSpaceNA",
                            "FloatByStopSize",
                        ],
                        "description": "光圈类型",
                    },
                    "value": {"type": "number", "description": "光圈值"},
                },
                "required": ["aperture_type", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_fields",
            "description": "设置系统视场（会清除并替换所有现有视场点）",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_type": {
                        "type": "string",
                        "enum": [
                            "Angle",
                            "ObjectHeight",
                            "ParaxialImageHeight",
                            "RealImageHeight",
                        ],
                        "description": "视场类型",
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number", "description": "X 视场值"},
                                "y": {"type": "number", "description": "Y 视场值"},
                                "weight": {
                                    "type": "number",
                                    "description": "权重 (默认 1.0)",
                                },
                            },
                            "required": ["x", "y"],
                        },
                        "description": "视场点列表",
                    },
                },
                "required": ["field_type", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_wavelengths",
            "description": "设置系统波长（会清除并替换所有现有波长）",
            "parameters": {
                "type": "object",
                "properties": {
                    "wavelengths": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "value": {
                                    "type": "number",
                                    "description": "波长值 (微米)",
                                },
                                "weight": {
                                    "type": "number",
                                    "description": "权重 (默认 1.0)",
                                },
                            },
                            "required": ["value"],
                        },
                        "description": "波长列表",
                    },
                    "preset": {
                        "type": "string",
                        "enum": ["d_light", "C_light", "F_light", "FdC_Visible"],
                        "description": "使用预设波长 (设置此项时忽略 wavelengths)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_variable",
            "description": "将指定表面的某个参数设为变量 (可优化) 或固定",
            "parameters": {
                "type": "object",
                "properties": {
                    "surface_number": {
                        "type": "integer",
                        "description": "表面编号",
                    },
                    "param": {
                        "type": "string",
                        "enum": ["radius", "thickness", "conic"],
                        "description": "参数名称",
                    },
                    "variable": {
                        "type": "boolean",
                        "description": "true=变量, false=固定",
                    },
                },
                "required": ["surface_number", "param", "variable"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_optimization",
            "description": "运行局部优化（阻尼最小二乘法 DLS 或正交下降 OD）",
            "parameters": {
                "type": "object",
                "properties": {
                    "algorithm": {
                        "type": "string",
                        "enum": ["DLS", "OD"],
                        "description": "DLS=阻尼最小二乘, OD=正交下降 (默认 DLS)",
                    },
                    "cycles": {
                        "type": "string",
                        "enum": [
                            "Automatic",
                            "Fixed_1",
                            "Fixed_5",
                            "Fixed_10",
                            "Fixed_50",
                        ],
                        "description": "循环次数 (默认 Automatic)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quick_focus",
            "description": "运行快速聚焦 (调整像面位置使 RMS 光斑最小)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_merit_function",
            "description": "获取当前评价函数值",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "new_file",
            "description": "新建一个空的光学系统 (会丢失未保存的更改)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_file",
            "description": "保存当前光学系统",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "另存为的完整路径 (.zmx)，不提供则保存到当前路径",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_file",
            "description": "打开指定的 .zmx 光学系统文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": ".zmx 文件的完整路径",
                    }
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_surface_type",
            "description": "设置表面类型 (如 Standard, EvenAsphere, Paraxial 等)",
            "parameters": {
                "type": "object",
                "properties": {
                    "surface_number": {
                        "type": "integer",
                        "description": "表面编号",
                    },
                    "surface_type": {
                        "type": "string",
                        "description": "表面类型名称，如 Standard, EvenAsphere, Paraxial, IdealLens 等",
                    },
                },
                "required": ["surface_number", "surface_type"],
            },
        },
    },
    # ----- 评价函数编辑工具 -----
    {
        "type": "function",
        "function": {
            "name": "set_default_merit_function",
            "description": (
                "使用序列优化向导设置默认评价函数（会覆盖从 start_at 行开始的内容）。"
                "这是设置标准成像评价函数最快捷的方式。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opt_type": {
                        "type": "integer",
                        "description": "优化类型: 0=RMS(均方根), 1=PTV(峰谷值)",
                    },
                    "data": {
                        "type": "integer",
                        "description": "优化数据: 0=波前(Wavefront), 1=光斑半径(SpotRadius), 2=光斑X, 3=光斑Y, 4=角度空间光斑",
                    },
                    "reference": {
                        "type": "integer",
                        "description": "参考: 0=质心(Centroid), 1=主光线(ChiefRay), 2=无参考",
                    },
                    "rings": {
                        "type": "integer",
                        "description": "环数: 0=1, 1=2, 2=3, 3=4, 4=5, 5=6",
                    },
                    "arms": {
                        "type": "integer",
                        "description": "臂数: 0=6, 1=8, 2=10, 3=12",
                    },
                    "use_glass_thickness": {
                        "type": "boolean",
                        "description": "是否添加玻璃厚度约束",
                    },
                    "glass_min": {"type": "number", "description": "玻璃最小中心厚度(mm)"},
                    "glass_max": {"type": "number", "description": "玻璃最大中心厚度(mm)"},
                    "use_air_thickness": {
                        "type": "boolean",
                        "description": "是否添加空气间隔约束",
                    },
                    "air_min": {"type": "number", "description": "空气最小间隔(mm)"},
                    "air_max": {"type": "number", "description": "空气最大间隔(mm)"},
                    "overall_weight": {"type": "number", "description": "整体权重 (默认 1.0)"},
                    "start_at": {
                        "type": "integer",
                        "description": "从MFE第几行开始覆盖 (默认 1=全部覆盖)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_operand",
            "description": (
                "向评价函数编辑器(MFE)添加一个操作数行。"
                "常用操作数: "
                "EFFL(有效焦距,Int1=波长号), "
                "EFLY(Y方向焦距), "
                "BFL(后焦距), "
                "TOTR(总长,Int1=起始面,Int2=终止面), "
                "TTHI(总玻璃厚度,Int1=起始面,Int2=终止面), "
                "MNCT(最小中心厚度), MXCT(最大中心厚度), "
                "MNEG(最小边缘厚度), MXEG(最大边缘厚度), "
                "DIMX(最大畸变%), AXCL(轴向色差), LACL(横向色差), "
                "PETC(Petzval曲率), OPTH(光程差)。"
                "weight=0 表示仅监视不参与优化。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operand_type": {
                        "type": "string",
                        "description": "操作数类型名称(4字母代码)，如 EFFL, BFL, TOTR 等",
                    },
                    "target": {"type": "number", "description": "目标值"},
                    "weight": {
                        "type": "number",
                        "description": "权重 (0=仅监视, >0=参与优化)。默认 1.0",
                    },
                    "int1": {
                        "type": "integer",
                        "description": "整数参数1 (含义取决于操作数类型，常为表面号或波长号，0=默认)",
                    },
                    "int2": {
                        "type": "integer",
                        "description": "整数参数2 (含义取决于操作数类型，常为波长号或视场号，0=默认)",
                    },
                },
                "required": ["operand_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_operands",
            "description": "获取评价函数编辑器(MFE)中所有操作数行的详细信息（类型/目标/权重/当前值）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_operands",
            "description": "从评价函数编辑器(MFE)中删除操作数。可删除指定行号或清除全部",
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要删除的行号列表(1-based)。不提供则清除所有操作数",
                    },
                },
                "required": [],
            },
        },
    },
    # ----- 系统分析工具 -----
    {
        "type": "function",
        "function": {
            "name": "get_first_order_data",
            "description": (
                "计算并获取系统一阶光学参数：有效焦距(EFFL)、后焦距(BFL)、总长(TOTR)。"
                "通过在MFE末尾临时插入监视操作数来计算，不影响现有评价函数。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ----- 玻璃库管理工具 -----
    {
        "type": "function",
        "function": {
            "name": "get_glass_catalogs",
            "description": (
                "获取玻璃库（材料目录）信息：当前使用的目录列表、系统中所有可用的目录列表。"
                "可选：查询某个目录中的所有材料名称。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "catalog": {
                        "type": "string",
                        "description": "要查询材料列表的目录名称（如 SCHOTT, OHARA, HOYA 等）。不提供则只返回目录列表。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_glass_catalogs",
            "description": (
                "管理系统使用的玻璃库（材料目录）：添加或移除目录。"
                "添加前会检查该目录是否可用，移除前会检查是否正在使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "add": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要添加的目录名称列表，如 [\"SCHOTT\", \"OHARA\"]",
                    },
                    "remove": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要移除的目录名称列表",
                    },
                },
                "required": [],
            },
        },
    },
    # ----- UI 刷新与布局工具 -----
    {
        "type": "function",
        "function": {
            "name": "update_ui",
            "description": (
                "刷新 OpticStudio 图形界面。调用后 GUI 中已打开的编辑器和分析窗口都会更新显示。"
                "在通过 API 修改系统后调用此工具可使 LDE、2D Layout 等窗口同步刷新。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_layout",
            "description": (
                "在 OpticStudio GUI 中打开一个新的 2D 或 3D 布局图窗口，显示当前光学系统结构。"
                "窗口会自动计算并渲染。可选择将图像导出到文件 (.bmp/.wmf)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layout_type": {
                        "type": "string",
                        "enum": ["2D", "3D"],
                        "description": "布局类型: 2D=横截面, 3D=三维视图 (默认 2D)",
                    },
                    "export_path": {
                        "type": "string",
                        "description": "可选：导出图像的文件路径 (支持 .bmp/.wmf)。不提供则只在 GUI 中显示。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_image_quality",
            "description": (
                "获取当前系统各视场的成像质量定量指标：RMS 弥散斑半径 (μm)、RMS 波前误差 (waves)，"
                "并计算艾里斑半径、判断是否达到衍射极限 (Marechal 准则 RMS < λ/14)。"
                "这是设计验收的核心评估工具，建议每轮优化后调用以确认是否满足 SPT 指标。"
                "注意：RSCE/RWCE 操作数使用当前 MFE 的采样配置；若未设置评价函数，"
                "建议先调用 set_default_merit_function 以配置有效采样。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wave": {
                        "type": "integer",
                        "description": "波长编号 (1-N)；0 = 多色综合 (默认)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_aberrations",
            "description": (
                "获取系统三阶塞德尔像差系数（球差 W040、慧差 W131、像散 W222、"
                "场曲 W220、畸变 W311，单位 λ）以及轴向色差 (mm) 和横向色差。"
                "通过 dominant_aberration 字段可知哪种像差主导，从而指导优化策略。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_distortion",
            "description": (
                "获取多个归一化视场高度处的几何畸变 (%) 数据。"
                "目视系统要求 < 5%；显微镜系统通常要求 < 1%；测量仪器要求 < 0.1%。"
                "返回最大畸变值和逐视场采样表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "num_points": {
                        "type": "integer",
                        "description": "沿视场方向采样点数量 (3-11)，默认 5",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mtf",
            "description": (
                "获取指定空间频率 (cycles/mm) 处各视场的 MTF 值（切向 T / 弧矢 S），"
                "并与理论衍射极限 MTF 比较。"
                "衍射截止频率 = 2×NA/λ_primary；超出截止频率则 MTF 理论为 0。"
                "建议在衍射截止频率的 0.5 倍处检查 MTF 以判断是否达到衍射极限。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frequency": {
                        "type": "number",
                        "description": "空间频率 (cycles/mm，线对/毫米)",
                    },
                    "wave": {
                        "type": "integer",
                        "description": "波长编号 (1-N)；0 = 多色综合 (默认)",
                    },
                },
                "required": ["frequency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mtf_curve",
            "description": (
                "在多个空间频率点（0 到截止频率之间均匀采样）计算 MTF，返回完整曲线数据，"
                "同时给出衍射极限 MTF 曲线用于对比。"
                "比单次 get_mtf 调用更全面，适合验收阶段评估系统传递函数曲线整体形状。"
                "返回：各频率点各视场 T/S MTF，以及衍射极限理论值列表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "num_points": {
                        "type": "integer",
                        "description": "频率采样点数量 (3-10)，默认 5",
                    },
                    "max_frequency": {
                        "type": "number",
                        "description": "最大频率上限 (cycles/mm)；0 = 自动取衍射截止频率",
                    },
                    "wave": {
                        "type": "integer",
                        "description": "波长编号 (1-N)；0 = 多色综合 (默认)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_manufacturability",
            "description": (
                "对当前光学系统进行可制造性检查，输出每个透镜元件的加工关键指标：\n"
                "• 中心厚度（CT）和边缘厚度（ET）\n"
                "• CT/ET 比值（极端比值难以加工）\n"
                "• 透镜弯曲因子 B = (R2+R1)/(R2-R1)（极端弯月形）\n"
                "• 最小曲率半径是否可抛光（< 3mm 视为危险）\n"
                "• 最大半口径与中心厚度之比（纤薄透镜风险）\n"
                "对每个问题项给出具体警告，并给出综合评分 pass/warn/fail。\n"
                "建议在每次优化结束后调用，防止优化器造出无法加工的镜片。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
#  工具实现
# ---------------------------------------------------------------------------


class ZemaxToolkit:
    """封装所有 Zemax 工具的调用逻辑."""

    def __init__(self, conn: ZemaxConnection):
        self.conn = conn

    # ---- 分发 (带自动重连) ----
    def dispatch(self, tool_name: str, arguments: dict) -> str:
        """根据工具名调用对应方法，返回 JSON 字符串结果.

        如果检测到 COM 连接断开，会自动尝试重连后再执行工具。
        """
        fn = getattr(self, tool_name, None)
        if fn is None:
            logger.warning(f"未知工具调用: {tool_name}")
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

        # 执行前检测连接状态
        if not self.conn.is_alive:
            logger.warning(f"工具 {tool_name} 执行前检测到连接丢失，尝试自动重连")
            print("\033[33m  [连接丢失] 正在尝试自动重连...\033[0m")
            if not self.conn.reconnect():
                logger.error("自动重连失败，工具执行中止")
                return json.dumps(
                    {"error": "OpticStudio 连接已断开且无法自动重连。请在 Zemax 中重新打开 Interactive Extension，然后输入 reconnect 手动重连。"},
                    ensure_ascii=False,
                )
            logger.info("自动重连成功，继续执行工具")
            print("\033[32m  [已重连] 继续执行工具...\033[0m")

        try:
            result = fn(**arguments)
            result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
            # 工具执行成功后自动刷新 UI（仅对写操作工具）
            if tool_name not in _READ_ONLY_TOOLS:
                self._auto_refresh_ui()
            return result_str
        except Exception as e:
            err_str = str(e)
            # 检测 COM 断连类异常，尝试重连后重试一次
            if _is_com_disconnect_error(err_str):
                logger.warning(f"工具 {tool_name} 触发 COM 断连异常，尝试重连: {err_str[:200]}")
                print("\033[33m  [COM 异常] 连接可能已断开，尝试重连...\033[0m")
                if self.conn.reconnect():
                    try:
                        result = fn(**arguments)
                        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
                        if tool_name not in _READ_ONLY_TOOLS:
                            self._auto_refresh_ui()
                        return result_str
                    except Exception as e2:
                        logger.error(f"工具 {tool_name} 重连后再次失败: {e2}", exc_info=True)
                        return json.dumps(
                            {"error": str(e2), "traceback": traceback.format_exc()},
                            ensure_ascii=False,
                        )
            logger.error(f"工具 {tool_name} 执行失败: {err_str[:300]}")
            return json.dumps(
                {"error": err_str, "traceback": traceback.format_exc()},
                ensure_ascii=False,
            )

    def _auto_refresh_ui(self) -> None:
        """工具执行后自动刷新 OpticStudio GUI（静默，不抛出异常）.

        策略：
        1. 调用 UpdateStatus() 刷新主窗口 (LDE / 系统编辑器)
        2. 如果有任何已打开的分析窗口，逐一调用 ApplyAndWaitForCompletion() 重算并刷新
        """
        try:
            system = self.conn.system
            try:
                system.UpdateStatus()
            except Exception:
                pass
            try:
                analyses = system.Analyses
                n = _safe(analyses, "NumberOfAnalyses", 0)
                for i in range(1, n + 1):
                    try:
                        a = analyses.Get_AnalysisAtIndex(i)
                        if a is not None:
                            a.ApplyAndWaitForCompletion()
                    except Exception:
                        continue
            except Exception:
                pass
        except Exception:
            pass

    # ---- 系统信息 ----
    def get_system_info(self) -> str:
        sys_data = self.conn.system_data
        lde = self.conn.lde

        # 光圈
        aperture_info = {
            "type": str(sys_data.Aperture.ApertureType),
            "value": sys_data.Aperture.ApertureValue,
        }

        # 视场 (通过安全访问层读取)
        fields_info = []
        for i in range(1, sys_data.Fields.NumberOfFields + 1):
            f = sys_data.Fields.GetField(i)
            x, y, weight = self.conn.get_field_data(f)
            fields_info.append({"index": i, "x": x, "y": y, "weight": weight})

        # 波长 (通过安全访问层读取)
        wavelengths_info = []
        for i in range(1, sys_data.Wavelengths.NumberOfWavelengths + 1):
            w = sys_data.Wavelengths.GetWavelength(i)
            value, weight = self.conn.get_wavelength_data(w)
            wavelengths_info.append({"index": i, "value_um": value, "weight": weight})

        # 表面
        surfaces = []
        num_surf = lde.NumberOfSurfaces
        for i in range(num_surf):
            surf = lde.GetSurfaceAt(i)
            surfaces.append(
                {
                    "number": i,
                    "comment": _safe(surf, "Comment", ""),
                    "radius": _safe(surf, "Radius", None),
                    "thickness": _safe(surf, "Thickness", None),
                    "material": _safe(surf, "Material", ""),
                    "semi_diameter": _safe(surf, "SemiDiameter", None),
                    "conic": _safe(surf, "Conic", 0.0),
                    "is_stop": _safe(surf, "IsStop", False),
                }
            )

        info = {
            "num_surfaces": num_surf,
            "aperture": aperture_info,
            "fields": fields_info,
            "wavelengths": wavelengths_info,
            "surfaces": surfaces,
        }
        return json.dumps(info, ensure_ascii=False, indent=2)

    # ---- 表面操作 ----
    def insert_surface(self, position: int) -> str:
        lde = self.conn.lde
        lde.InsertNewSurfaceAt(position)
        return json.dumps({"ok": True, "message": f"已在位置 {position} 插入新表面"}, ensure_ascii=False)

    def edit_surface(self, surface_number: int, **kwargs) -> str:
        lde = self.conn.lde
        surf = lde.GetSurfaceAt(surface_number)
        changed = []

        if "radius" in kwargs and kwargs["radius"] is not None:
            surf.Radius = float(kwargs["radius"])
            changed.append(f"radius={kwargs['radius']}")

        if "thickness" in kwargs and kwargs["thickness"] is not None:
            surf.Thickness = float(kwargs["thickness"])
            changed.append(f"thickness={kwargs['thickness']}")

        if "material" in kwargs and kwargs["material"] is not None:
            surf.Material = str(kwargs["material"])
            changed.append(f"material={kwargs['material']}")

        if "semi_diameter" in kwargs and kwargs["semi_diameter"] is not None:
            surf.SemiDiameter = float(kwargs["semi_diameter"])
            changed.append(f"semi_diameter={kwargs['semi_diameter']}")

        if "conic" in kwargs and kwargs["conic"] is not None:
            surf.Conic = float(kwargs["conic"])
            changed.append(f"conic={kwargs['conic']}")

        if "comment" in kwargs and kwargs["comment"] is not None:
            surf.Comment = str(kwargs["comment"])
            changed.append(f"comment={kwargs['comment']}")

        if "is_stop" in kwargs and kwargs["is_stop"] is not None:
            if kwargs["is_stop"]:
                surf.IsStop = True
                changed.append("is_stop=True")

        return json.dumps(
            {"ok": True, "surface": surface_number, "changed": changed},
            ensure_ascii=False,
        )

    def remove_surface(self, surface_number: int) -> str:
        lde = self.conn.lde
        num = lde.NumberOfSurfaces
        if surface_number <= 0 or surface_number >= num - 1:
            return json.dumps(
                {"error": f"无法删除物面(0)或像面({num - 1})"},
                ensure_ascii=False,
            )
        lde.RemoveSurfaceAt(surface_number)
        return json.dumps({"ok": True, "message": f"已删除面 {surface_number}"}, ensure_ascii=False)

    def set_surface_type(self, surface_number: int, surface_type: str) -> str:
        lde = self.conn.lde
        surf = lde.GetSurfaceAt(surface_number)
        type_settings = surf.GetSurfaceTypeSettings(surf.TypeName)
        # 尝试通过名称查找类型
        try:
            type_settings = surf.GetSurfaceTypeSettings(surface_type)
            surf.ChangeType(type_settings)
        except Exception:
            return json.dumps(
                {"error": f"无法将面 {surface_number} 改为类型 '{surface_type}'，请检查类型名称"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": True, "message": f"面 {surface_number} 类型已改为 {surface_type}"},
            ensure_ascii=False,
        )

    # ---- 光圈 ----
    def set_aperture(self, aperture_type: str, value: float) -> str:
        aperture_map = {
            "EntrancePupilDiameter": 0,
            "ImageSpaceFNumber": 1,
            "ObjectSpaceNA": 2,
            "FloatByStopSize": 3,
        }
        sys_data = self.conn.system_data
        apt = sys_data.Aperture
        type_val = aperture_map.get(aperture_type, 0)
        apt.ApertureType = type_val
        apt.ApertureValue = value
        return json.dumps(
            {"ok": True, "aperture_type": aperture_type, "value": value},
            ensure_ascii=False,
        )

    # ---- 视场 ----
    def set_fields(self, field_type: str, fields: list) -> str:
        field_type_map = {
            "Angle": 0,
            "ObjectHeight": 1,
            "ParaxialImageHeight": 2,
            "RealImageHeight": 3,
        }
        sys_data = self.conn.system_data
        flds = sys_data.Fields

        # 设置视场类型
        type_val = field_type_map.get(field_type, 0)
        try:
            flds.SetFieldType(type_val)
        except Exception:
            pass  # 部分版本可能不支持

        # 清除现有视场 (保留至少1个)
        while flds.NumberOfFields > 1:
            flds.RemoveField(flds.NumberOfFields)

        # 设置第一个视场 (通过安全访问层)
        if fields:
            f0 = fields[0]
            first = flds.GetField(1)
            self.conn.set_field_data(first, x=f0.get("x", 0.0), y=f0.get("y", 0.0), weight=f0.get("weight", 1.0))

        # 添加其余视场
        for f in fields[1:]:
            flds.AddField(f.get("x", 0.0), f.get("y", 0.0), f.get("weight", 1.0))

        return json.dumps(
            {"ok": True, "field_type": field_type, "count": len(fields)},
            ensure_ascii=False,
        )

    # ---- 波长 ----
    def set_wavelengths(self, wavelengths: list = None, preset: str = None) -> str:
        sys_data = self.conn.system_data
        wls = sys_data.Wavelengths

        if preset:
            preset_map = {
                "d_light": 3,     # d-光 0.5876 μm
                "C_light": 2,     # C-光 0.6563 μm
                "F_light": 1,     # F-光 0.4861 μm
                "FdC_Visible": 4,  # F, d, C 三波长
            }
            val = preset_map.get(preset, 3)
            try:
                wls.SelectWavelengthPreset(val)
            except Exception as e:
                return json.dumps({"error": f"预设波长设置失败: {e}"}, ensure_ascii=False)
            return json.dumps({"ok": True, "preset": preset}, ensure_ascii=False)

        if not wavelengths:
            return json.dumps({"error": "需要提供 wavelengths 或 preset"}, ensure_ascii=False)

        # 清除现有波长
        while wls.NumberOfWavelengths > 1:
            wls.RemoveWavelength(wls.NumberOfWavelengths)

        # 设置第一个波长 (通过安全访问层)
        w0 = wavelengths[0]
        first = wls.GetWavelength(1)
        self.conn.set_wavelength_data(first, value=w0["value"], weight=w0.get("weight", 1.0))

        # 添加其余波长
        for w in wavelengths[1:]:
            wls.AddWavelength(w["value"], w.get("weight", 1.0))

        return json.dumps(
            {"ok": True, "count": len(wavelengths)},
            ensure_ascii=False,
        )

    # ---- 变量 ----
    def make_variable(self, surface_number: int, param: str, variable: bool) -> str:
        lde = self.conn.lde
        surf = lde.GetSurfaceAt(surface_number)

        cell_map = {
            "radius": "RadiusCell",
            "thickness": "ThicknessCell",
            "conic": "ConicCell",
        }
        cell_attr = cell_map.get(param)
        if not cell_attr:
            return json.dumps({"error": f"不支持的参数: {param}"}, ensure_ascii=False)

        cell = getattr(surf, cell_attr)
        if variable:
            cell.MakeSolveVariable()
        else:
            cell.MakeSolveFixed()

        status = "变量" if variable else "固定"
        return json.dumps(
            {"ok": True, "message": f"面 {surface_number} 的 {param} 已设为{status}"},
            ensure_ascii=False,
        )

    # ---- 优化 ----
    def run_optimization(self, algorithm: str = "DLS", cycles: str = "Automatic") -> str:
        from win32com.client import CastTo

        tools = self.conn.system.Tools
        opt = tools.OpenLocalOptimization()
        if opt is None:
            return json.dumps(
                {"error": "无法打开局部优化工具。可能原因: 1) 没有设置评价函数; 2) Zemax UI 中有其他工具窗口打开; 3) 没有变量。请关闭 Zemax 中的其他工具窗口后重试。"},
                ensure_ascii=False,
            )

        # 配置优化参数 (这些属性在 ILocalOptimization 接口上)
        if algorithm == "OD":
            _safe_set_attr(opt, "Algorithm", 1)  # OrthogonalDescent
        else:
            _safe_set_attr(opt, "Algorithm", 0)  # DampedLeastSquares

        cycles_map = {
            "Automatic": 0,
            "Fixed_1": 1,
            "Fixed_5": 5,
            "Fixed_10": 10,
            "Fixed_50": 50,
        }
        cycle_val = cycles_map.get(cycles, 0)
        if cycle_val == 0:
            _safe_set_attr(opt, "Cycles", -1)  # Automatic
        else:
            if not _safe_set_attr(opt, "NumberOfCycles", cycle_val):
                _safe_set_attr(opt, "Cycles", cycle_val)

        # RunAndWaitForCompletion / Close 在基类 ISystemTool 上
        # 参考 PyZOS inheritance_dict: ILocalOptimization -> ISystemTool
        tool_base = _cast_to_system_tool(opt)
        tool_base.RunAndWaitForCompletion()

        # CurrentMeritFunction 在 ILocalOptimization 上
        mfv = _safe(opt, "CurrentMeritFunction", None)

        tool_base.Close()

        return json.dumps(
            {"ok": True, "algorithm": algorithm, "cycles": cycles, "final_merit_function": mfv},
            ensure_ascii=False,
        )

    def quick_focus(self) -> str:
        from win32com.client import CastTo

        tools = self.conn.system.Tools
        qf = tools.OpenQuickFocus()
        if qf is None:
            return json.dumps(
                {"error": "无法打开快速聚焦工具。可能原因: Zemax UI 中有其他工具窗口打开。请关闭后重试。"},
                ensure_ascii=False,
            )

        # 配置参数 (IQuickFocus 接口上)
        _safe_set_attr(qf, "Criterion", 0)  # SpotSizeRadial
        _safe_set_attr(qf, "UseCentroid", True)

        # RunAndWaitForCompletion / Close 在基类 ISystemTool 上
        # 参考 PyZOS inheritance_dict: IQuickFocus -> ISystemTool
        tool_base = _cast_to_system_tool(qf)
        tool_base.RunAndWaitForCompletion()
        tool_base.Close()

        return json.dumps({"ok": True, "message": "快速聚焦完成"}, ensure_ascii=False)

    def get_merit_function(self) -> str:
        mfe = self.conn.mfe
        try:
            mfv = mfe.CalculateMeritFunction()
        except Exception:
            mfv = None
        return json.dumps({"merit_function_value": mfv}, ensure_ascii=False)

    # ---- 文件操作 ----
    def new_file(self) -> str:
        self.conn.system.New(False)
        return json.dumps({"ok": True, "message": "已创建新系统"}, ensure_ascii=False)

    def save_file(self, filename: str = None) -> str:
        if filename:
            self.conn.system.SaveAs(filename)
            return json.dumps({"ok": True, "message": f"已另存为 {filename}"}, ensure_ascii=False)
        else:
            self.conn.system.Save()
            return json.dumps({"ok": True, "message": "已保存"}, ensure_ascii=False)

    def open_file(self, filename: str) -> str:
        self.conn.system.LoadFile(filename, False)
        return json.dumps({"ok": True, "message": f"已打开 {filename}"}, ensure_ascii=False)

    # ---- 评价函数编辑 ----
    def set_default_merit_function(self, opt_type: int = 0, data: int = 1,
                                   reference: int = 0, rings: int = 3, arms: int = 3,
                                   use_glass_thickness: bool = False,
                                   glass_min: float = 0, glass_max: float = 1000,
                                   use_air_thickness: bool = False,
                                   air_min: float = 0, air_max: float = 1000,
                                   overall_weight: float = 1.0, start_at: int = 1) -> str:
        """使用序列优化向导设置默认评价函数 (参考 PyZOS zSetDefaultMeritFunctionSEQ)."""
        from win32com.client import CastTo

        mfe = self.conn.mfe
        wizard = _safe(mfe, "SEQOptimizationWizard", None)
        if wizard is None:
            return json.dumps(
                {"error": "无法获取序列优化向导 (SEQOptimizationWizard)。请确认 MFE 可用。"},
                ensure_ascii=False,
            )

        # 设置向导参数
        _safe_set_attr(wizard, "Type", opt_type)
        _safe_set_attr(wizard, "Data", data)
        _safe_set_attr(wizard, "Reference", reference)
        _safe_set_attr(wizard, "Ring", rings)
        _safe_set_attr(wizard, "Arm", arms)
        _safe_set_attr(wizard, "IsGlassUsed", use_glass_thickness)
        _safe_set_attr(wizard, "GlassMin", glass_min)
        _safe_set_attr(wizard, "GlassMax", glass_max)
        _safe_set_attr(wizard, "IsAirUsed", use_air_thickness)
        _safe_set_attr(wizard, "AirMin", air_min)
        _safe_set_attr(wizard, "AirMax", air_max)
        _safe_set_attr(wizard, "OverallWeight", overall_weight)
        _safe_set_attr(wizard, "StartAt", start_at)

        # 执行向导: ISEQOptimizationWizard -> IWizard (base)
        # CommonSettings.OK() 定义在 IWizard 上，需要 CastTo
        executed = False
        for attempt_fn in [
            lambda: CastTo(wizard, "IWizard").CommonSettings.OK(),
            lambda: wizard.CommonSettings.OK(),
            lambda: wizard.OK(),
            lambda: wizard.Apply(),
        ]:
            try:
                attempt_fn()
                executed = True
                break
            except Exception:
                continue

        if not executed:
            return json.dumps(
                {"error": "无法执行优化向导。所有已知执行方法均失败。"},
                ensure_ascii=False,
            )

        try:
            mfv = mfe.CalculateMeritFunction()
        except Exception:
            mfv = None

        return json.dumps(
            {
                "ok": True,
                "message": "默认评价函数已通过向导设置",
                "merit_function_value": mfv,
                "num_operands": _safe(mfe, "NumberOfOperands", None),
            },
            ensure_ascii=False,
        )

    def add_operand(self, operand_type: str, target: float = None,
                    weight: float = 1.0, int1: int = None, int2: int = None) -> str:
        """向 MFE 添加一个操作数行."""
        mfe = self.conn.mfe

        type_val = _resolve_operand_type(operand_type)
        if type_val is None:
            return json.dumps(
                {"error": f"未知操作数类型: '{operand_type}'。请使用标准4字母代码(如 EFFL, BFL, TOTR)。"},
                ensure_ascii=False,
            )

        # 在末尾插入新行
        num = _safe(mfe, "NumberOfOperands", 0)
        row = None
        try:
            row = mfe.InsertNewOperandAt(num + 1)
        except Exception:
            try:
                row = mfe.AddOperand()
            except Exception as e:
                return json.dumps({"error": f"无法插入新操作数行: {e}"}, ensure_ascii=False)

        if row is None:
            return json.dumps({"error": "插入新操作数行返回 None"}, ensure_ascii=False)

        # 设置操作数类型
        if not _set_row_operand_type(row, type_val):
            return json.dumps(
                {"error": f"无法设置操作数类型 {operand_type} (enum={type_val})"},
                ensure_ascii=False,
            )

        # 设置目标值和权重
        if target is not None:
            _safe_set_attr(row, "Target", float(target))
        if weight is not None:
            _safe_set_attr(row, "Weight", float(weight))

        # 设置整数参数
        if int1 is not None:
            _set_operand_int_param(row, 1, int(int1))
        if int2 is not None:
            _set_operand_int_param(row, 2, int(int2))

        # 计算获取当前值
        try:
            mfe.CalculateMeritFunction()
        except Exception:
            pass

        new_row_num = _safe(mfe, "NumberOfOperands", 0)
        current_row = mfe.GetOperandAt(new_row_num)
        current_value = _safe(current_row, "Value", None)

        return json.dumps(
            {
                "ok": True,
                "row": new_row_num,
                "type": operand_type,
                "target": target,
                "weight": weight,
                "current_value": current_value,
            },
            ensure_ascii=False,
        )

    def get_operands(self) -> str:
        """获取 MFE 中所有操作数详情."""
        mfe = self.conn.mfe
        num = _safe(mfe, "NumberOfOperands", 0)

        try:
            mf_value = mfe.CalculateMeritFunction()
        except Exception:
            mf_value = None

        operands = []
        for i in range(1, num + 1):
            row = mfe.GetOperandAt(i)
            op = {
                "row": i,
                "type": _safe(row, "TypeName", None) or str(_safe(row, "Type", "?")),
                "target": _safe(row, "Target", None),
                "weight": _safe(row, "Weight", None),
                "value": _safe(row, "Value", None),
            }
            p1 = _safe(row, "Param1", None)
            p2 = _safe(row, "Param2", None)
            if p1 is not None:
                op["int1"] = p1
            if p2 is not None:
                op["int2"] = p2
            operands.append(op)

        return json.dumps(
            {"merit_function_value": mf_value, "num_operands": num, "operands": operands},
            ensure_ascii=False,
            indent=2,
        )

    def remove_operands(self, rows: list = None) -> str:
        """从 MFE 删除指定行或清除所有操作数."""
        mfe = self.conn.mfe

        def _del(pos):
            try:
                mfe.DeleteOperandAt(pos)
                return
            except (AttributeError, Exception):
                pass
            mfe.RemoveOperandAt(pos)

        if rows:
            for row_num in sorted(rows, reverse=True):
                _del(row_num)
            return json.dumps(
                {"ok": True, "message": f"已删除 {len(rows)} 行操作数"},
                ensure_ascii=False,
            )
        else:
            count = 0
            num = _safe(mfe, "NumberOfOperands", 0)
            while num > 1:
                _del(num)
                count += 1
                num = _safe(mfe, "NumberOfOperands", 0)
            return json.dumps(
                {"ok": True, "message": f"已清除 {count} 行操作数，剩余 {num} 行"},
                ensure_ascii=False,
            )

    # ---- 系统分析 ----
    def get_first_order_data(self) -> str:
        """通过临时 MFE 操作数计算一阶光学参数 (不影响现有评价函数)."""
        mfe = self.conn.mfe
        orig_num = _safe(mfe, "NumberOfOperands", 0)

        calc_ops = [
            ("EFFL", "有效焦距 (mm)"),
            ("BFL", "后焦距 (mm)"),
            ("TOTR", "总长 (mm)"),
        ]

        # 在 MFE 末尾添加临时监视操作数
        added = []
        for op_name, _ in calc_ops:
            type_val = _resolve_operand_type(op_name)
            if type_val is None:
                continue
            try:
                pos = _safe(mfe, "NumberOfOperands", 0) + 1
                row = mfe.InsertNewOperandAt(pos)
            except Exception:
                try:
                    row = mfe.AddOperand()
                except Exception:
                    continue
            if row is None:
                continue

            _set_row_operand_type(row, type_val)
            _safe_set_attr(row, "Weight", 0.0)
            _safe_set_attr(row, "Target", 0.0)
            added.append((op_name, _safe(mfe, "NumberOfOperands", 0)))

        # 计算
        try:
            mf_value = mfe.CalculateMeritFunction()
        except Exception:
            mf_value = None

        # 读取结果
        data = {}
        for op_name, row_num in added:
            try:
                row = mfe.GetOperandAt(row_num)
                data[op_name] = _safe(row, "Value", None)
            except Exception:
                data[op_name] = None

        # 清除临时操作数 (逆序删除)
        for _, row_num in reversed(added):
            try:
                mfe.DeleteOperandAt(row_num)
            except Exception:
                try:
                    mfe.RemoveOperandAt(row_num)
                except Exception:
                    pass

        display = {}
        for op_name, label in calc_ops:
            if op_name in data:
                display[op_name] = {"label": label, "value": data[op_name]}

        return json.dumps(
            {"first_order_data": display, "merit_function_value": mf_value},
            ensure_ascii=False,
            indent=2,
        )

    # ---- 成像质量分析 ----

    def get_image_quality(self, wave: int = 0) -> str:
        """各视场 RMS 弥散斑半径、RMS 波前误差，并判断是否达到衍射极限。

        使用临时 MFE 操作数读取数值 (不修改现有评价函数)。

        操作数说明：
          RSCE(surf=last, wave=w, hx=0, hy=Hn, px=0, py=0) → RMS 弥散斑半径 (μm，质心参考)
          RWCE(surf=last, wave=w, hx=0, hy=Hn, px=0, py=0) → RMS 波前误差 (waves，质心参考)
          ISNA → 像方 NA（用于艾里斑计算）
        """
        mfe = self.conn.mfe
        sys_data = self.conn.system_data
        lde = self.conn.lde

        # 读取系统参数
        num_fields = sys_data.Fields.NumberOfFields
        num_waves = sys_data.Wavelengths.NumberOfWavelengths
        last_surf = lde.NumberOfSurfaces - 1  # 像面索引

        # 主波长（取中间波长）
        primary_wave_idx = (num_waves + 1) // 2  # e.g. 3波长 → index 2
        primary_wave_um = None
        try:
            w_obj = sys_data.Wavelengths.GetWavelength(primary_wave_idx)
            primary_wave_um, _ = self.conn.get_wavelength_data(w_obj)
        except Exception:
            primary_wave_um = 0.5876  # 默认 d 线

        wave_param = wave  # 0=多色, 1..N=单色

        # 检测镜头单位并计算 RSCE→μm 换算因子
        # RSCE 操作数返回值的单位与镜头单位一致 (mm→需乘1000, cm→10000, etc.)
        # ScaleToUnits enum: Millimeters=0, Centimeters=1, Inches=2, Meters=3
        lens_unit_to_um = 1000.0  # 默认 mm
        try:
            units_obj = _safe(sys_data, "Units", None)
            if units_obj is not None:
                lu = _safe(units_obj, "LensUnits", None)
                if lu == 0:   lens_unit_to_um = 1000.0   # mm → μm
                elif lu == 1: lens_unit_to_um = 10000.0  # cm → μm
                elif lu == 2: lens_unit_to_um = 25400.0  # inches → μm
                elif lu == 3: lens_unit_to_um = 1e6      # m → μm
        except Exception:
            pass

        # --- 逐视场添加临时操作数 ---
        added = []  # (field_idx, op_name, row_num)

        def _add_tmp(op_name, int_params: dict):
            """在 MFE 末尾添加临时操作数，返回行号或 None。"""
            type_val = _resolve_operand_type(op_name)
            if type_val is None:
                return None
            pos = _safe(mfe, "NumberOfOperands", 0) + 1
            row = None
            try:
                row = mfe.InsertNewOperandAt(pos)
            except Exception:
                try:
                    row = mfe.AddOperand()
                except Exception:
                    return None
            if row is None:
                return None
            _set_row_operand_type(row, type_val)
            _safe_set_attr(row, "Weight", 0.0)
            _safe_set_attr(row, "Target", 0.0)
            # 整数参数: Param1=surf, Param2=wave, Param3=field(对于场相关操作数)
            for pnum, pval in int_params.items():
                _set_operand_int_param(row, pnum, pval)
            return _safe(mfe, "NumberOfOperands", 0)

        # ISNA
        isna_row = _add_tmp("ISNA", {})
        added.append(("ISNA", isna_row))

        # RSCE / RWCE per field
        # RSCE: Param1=surf, Param2=wave; 视场通过 Hx/Hy 指定（用 MFE Cell 设置）
        # 更简单的方式: 对每个视场，用 Hy=field_norm_y 的方式
        # ZOS-API MFE RSCE 参数: Int1=surf, Int2=wave, Hx,Hy,Px,Py 在 GetOperandCell
        # 实际上 Zemax 对 RSCE 的 Hy 是归一化视场高度; 最简单是用 Param3=field_idx
        # 但不同版本可能不同；保险方式: 使用 Param2=field, Param1=wave 类似 MTFT

        # 使用较通用方式: RSCE(Int1=last_surf, Int2=wave, Hx=0, Hy=Hn)
        # 通过 GetOperandCell 设置 Hx/Hy/Px/Py
        def _set_cell(row_obj, col_idx, float_val=None, int_val=None):
            try:
                cell = row_obj.GetOperandCell(col_idx)
                if cell is None:
                    return
                if float_val is not None:
                    try:
                        cell.DoubleValue = float_val
                    except Exception:
                        try:
                            cell.Value = float_val
                        except Exception:
                            pass
                if int_val is not None:
                    try:
                        cell.IntegerValue = int_val
                    except Exception:
                        try:
                            cell.Value = int_val
                        except Exception:
                            pass
            except Exception:
                pass

        # RSCE / RWCE col layout (0-indexed from GetOperandCell):
        # col 1 = Type, col 2 = Int1(surf), col 3 = Int2(wave),
        # col 4 = Hx, col 5 = Hy, col 6 = Px, col 7 = Py
        rsce_rows = []
        rwce_rows = []
        for fi in range(1, num_fields + 1):
            f_obj = sys_data.Fields.GetField(fi)
            _, fy, _ = self.conn.get_field_data(f_obj)
            # 归一化视场高度 (假设最大视场 = 1)
            max_fy = 1.0
            try:
                fm = sys_data.Fields.GetField(num_fields)
                _, max_fy_raw, _ = self.conn.get_field_data(fm)
                if max_fy_raw and max_fy_raw != 0:
                    max_fy = abs(max_fy_raw)
            except Exception:
                pass
            hy_norm = (fy / max_fy) if max_fy != 0 else 0.0

            # RSCE row
            type_val_rsce = _resolve_operand_type("RSCE")
            if type_val_rsce is not None:
                pos = _safe(mfe, "NumberOfOperands", 0) + 1
                row = None
                try:
                    row = mfe.InsertNewOperandAt(pos)
                except Exception:
                    try:
                        row = mfe.AddOperand()
                    except Exception:
                        pass
                if row is not None:
                    _set_row_operand_type(row, type_val_rsce)
                    # ChangeType 后重新获取引用，防止旧引用失效
                    row = _refetch_last_row(mfe) or row
                    _safe_set_attr(row, "Weight", 0.0)
                    _safe_set_attr(row, "Target", 0.0)
                    _set_operand_int_param(row, 1, last_surf)   # Param1=surf
                    _set_operand_int_param(row, 2, wave_param)  # Param2=wave
                    # Hx=Param3(col4)=0, Hy=Param4(col5)=hy_norm
                    _set_operand_double_param(row, 3, 0.0)           # Hx
                    _set_operand_double_param(row, 4, float(hy_norm)) # Hy
                    rsce_rows.append((fi, fy, _safe(mfe, "NumberOfOperands", 0)))

            # RWCE row
            type_val_rwce = _resolve_operand_type("RWCE")
            if type_val_rwce is not None:
                pos = _safe(mfe, "NumberOfOperands", 0) + 1
                row = None
                try:
                    row = mfe.InsertNewOperandAt(pos)
                except Exception:
                    try:
                        row = mfe.AddOperand()
                    except Exception:
                        pass
                if row is not None:
                    _set_row_operand_type(row, type_val_rwce)
                    row = _refetch_last_row(mfe) or row
                    _safe_set_attr(row, "Weight", 0.0)
                    _safe_set_attr(row, "Target", 0.0)
                    _set_operand_int_param(row, 1, last_surf)   # Param1=surf
                    _set_operand_int_param(row, 2, wave_param)  # Param2=wave
                    # Hx=Param3(col4)=0, Hy=Param4(col5)=hy_norm
                    _set_operand_double_param(row, 3, 0.0)           # Hx
                    _set_operand_double_param(row, 4, float(hy_norm)) # Hy
                    rwce_rows.append((fi, fy, _safe(mfe, "NumberOfOperands", 0)))

        # --- 计算 ---
        try:
            mfe.CalculateMeritFunction()
        except Exception:
            pass

        # --- 读取 ISNA ---
        image_na = None
        if isna_row is not None:
            try:
                image_na = _safe(mfe.GetOperandAt(isna_row), "Value", None)
            except Exception:
                pass

        # 艾里斑半径 = 1.22 * λ / (2 * NA_image)，单位 μm
        # λ 已是 μm，结果直接是 μm，不需要再乘 1000
        airy_radius_um = None
        if image_na and image_na > 0 and primary_wave_um:
            airy_radius_um = round(1.22 * primary_wave_um / (2 * image_na), 4)

        # Marechal 准则: 衍射极限阈值 = λ/14 (in waves)
        marechal_threshold = 1 / 14.0  # ≈ 0.0714 waves

        # --- 读取 RSCE / RWCE ---
        fields_data = []
        rsce_dict = {}
        for fi, fy, rnum in rsce_rows:
            try:
                val = _safe(mfe.GetOperandAt(rnum), "Value", None)
                rsce_dict[fi] = val
            except Exception:
                rsce_dict[fi] = None

        rwce_dict = {}
        for fi, fy, rnum in rwce_rows:
            try:
                val = _safe(mfe.GetOperandAt(rnum), "Value", None)
                rwce_dict[fi] = val
            except Exception:
                rwce_dict[fi] = None

        for fi in range(1, num_fields + 1):
            f_obj = sys_data.Fields.GetField(fi)
            _, fy, _ = self.conn.get_field_data(f_obj)
            rms_spot_raw = rsce_dict.get(fi)  # 镜头单位 (mm)
            rms_spot = (rms_spot_raw * lens_unit_to_um) if rms_spot_raw is not None else None  # → μm
            rms_wfe = rwce_dict.get(fi)
            diffraction_limited = None
            if rms_wfe is not None:
                diffraction_limited = bool(rms_wfe < marechal_threshold)
            entry = {
                "field": fi,
                "field_y": fy,
                "rms_spot_um": round(rms_spot, 2) if rms_spot is not None else None,
                "rms_wavefront_waves": round(rms_wfe, 5) if rms_wfe is not None else None,
                "diffraction_limited": diffraction_limited,
            }
            if airy_radius_um is not None and rms_spot is not None:
                entry["vs_airy"] = round(rms_spot / airy_radius_um, 3)
            fields_data.append(entry)

        # --- 清除所有临时操作数 (逆序) ---
        all_tmp_rows = (
            [isna_row] if isna_row else []
        ) + [r for _, _, r in rsce_rows] + [r for _, _, r in rwce_rows]
        for rnum in sorted(set(all_tmp_rows), reverse=True):
            try:
                mfe.DeleteOperandAt(rnum)
            except Exception:
                try:
                    mfe.RemoveOperandAt(rnum)
                except Exception:
                    pass

        result = {
            "primary_wavelength_um": primary_wave_um,
            "image_na": image_na,
            "airy_radius_um": airy_radius_um,
            "marechal_threshold_waves": round(marechal_threshold, 4),
            "fields": fields_data,
        }

        # 汇总
        rms_spots = [f["rms_spot_um"] for f in fields_data if f["rms_spot_um"] is not None]
        if rms_spots:
            result["max_rms_spot_um"] = round(max(rms_spots), 4)
            result["all_diffraction_limited"] = all(
                f.get("diffraction_limited", False) for f in fields_data
                if f.get("diffraction_limited") is not None
            )

        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_aberrations(self) -> str:
        """获取三阶 Seidel 像差系数和色差 (临时 MFE 操作数方式)。

        操作数:
          SPHA → 三阶球差系数 W040 (waves)
          COMA → 三阶慧差 W131 (waves)
          ASTI → 三阶像散 W222 (waves)
          FCUR → 三阶场曲 W220 (waves)
          DIST → 三阶畸变 W311 (waves)
          AXCL → 轴向色差 (mm)
          LACL → 横向色差 (μm)

        所有操作数 Int1=0 表示对整个系统求和。
        """
        mfe = self.conn.mfe

        seidel_ops = [
            ("SPHA", "三阶球差 W040 (waves)"),
            ("COMA", "三阶慧差 W131 (waves)"),
            ("ASTI", "三阶像散 W222 (waves)"),
            ("FCUR", "三阶场曲 W220 (waves)"),
            ("DIST", "三阶畸变 W311 (waves)"),
            ("AXCL", "轴向色差 (mm)"),
            ("LACL", "横向色差 (μm)"),
        ]

        added = []
        for op_name, _ in seidel_ops:
            type_val = _resolve_operand_type(op_name)
            if type_val is None:
                continue
            pos = _safe(mfe, "NumberOfOperands", 0) + 1
            row = None
            try:
                row = mfe.InsertNewOperandAt(pos)
            except Exception:
                try:
                    row = mfe.AddOperand()
                except Exception:
                    continue
            if row is None:
                continue
            _set_row_operand_type(row, type_val)
            _safe_set_attr(row, "Weight", 0.0)
            _safe_set_attr(row, "Target", 0.0)
            _set_operand_int_param(row, 1, 0)  # surf=0: 全系统
            added.append((op_name, _safe(mfe, "NumberOfOperands", 0)))

        try:
            mfe.CalculateMeritFunction()
        except Exception:
            pass

        data = {}
        for op_name, rnum in added:
            try:
                data[op_name] = _safe(mfe.GetOperandAt(rnum), "Value", None)
            except Exception:
                data[op_name] = None

        # 清除
        for _, rnum in sorted(added, key=lambda x: x[1], reverse=True):
            try:
                mfe.DeleteOperandAt(rnum)
            except Exception:
                try:
                    mfe.RemoveOperandAt(rnum)
                except Exception:
                    pass

        # 构造结果
        aberrations = {}
        for op_name, label in seidel_ops:
            aberrations[op_name] = {
                "label": label,
                "value": round(data[op_name], 6) if data.get(op_name) is not None else None,
            }

        # 判断主导像差 (取绝对值最大的 Seidel 项)
        seidel_keys = ["SPHA", "COMA", "ASTI", "FCUR", "DIST"]
        dominant = None
        max_abs = 0.0
        for k in seidel_keys:
            v = data.get(k)
            if v is not None and abs(v) > max_abs:
                max_abs = abs(v)
                dominant = k

        result = {
            "aberrations": aberrations,
            "dominant_aberration": dominant,
            "dominant_value": round(max_abs, 6) if dominant else None,
            "tip": {
                "SPHA": "球差主导 → 检查正负透镜曲率分配，或释放更多曲率变量",
                "COMA": "慧差主导 → 检查孔径光阑位置，或调整弯月形状",
                "ASTI": "像散主导 → 调整透镜间距或视场采样",
                "FCUR": "场曲主导 → 引入平场元件或反向弯月透镜",
                "DIST": "畸变主导 → 对称结构可自消畸变，或在 MFE 加 DIST 约束",
            }.get(dominant, ""),
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_distortion(self, num_points: int = 5) -> str:
        """获取多视场归一化高度处的几何畸变 (%)。

        使用 MFE 操作数 DISC (distortion percentage):
          DISC(Int1=field, Int2=wave) → 该视场畸变百分比
        若 DISC 不可用，回退到 DIST (rays) 计算。
        """
        mfe = self.conn.mfe
        sys_data = self.conn.system_data
        num_fields = sys_data.Fields.NumberOfFields
        num_waves = sys_data.Wavelengths.NumberOfWavelengths
        primary_wave_idx = (num_waves + 1) // 2

        num_points = max(3, min(11, num_points))

        # 尝试 DISC 操作数
        type_val_disc = _resolve_operand_type("DISC")
        type_val_dimx = _resolve_operand_type("DIMX")  # 最大畸变

        added = []

        if type_val_disc is not None:
            # 按均匀归一化视场高度采样
            for fi in range(1, num_points + 1):
                # 将采样视场映射到实际视场编号范围
                field_idx = max(1, min(num_fields, round(1 + (fi - 1) * (num_fields - 1) / max(1, num_points - 1))))
                pos = _safe(mfe, "NumberOfOperands", 0) + 1
                row = None
                try:
                    row = mfe.InsertNewOperandAt(pos)
                except Exception:
                    try:
                        row = mfe.AddOperand()
                    except Exception:
                        continue
                if row is None:
                    continue
                _set_row_operand_type(row, type_val_disc)
                # ChangeType 后重新获取引用
                row = _refetch_last_row(mfe) or row
                _safe_set_attr(row, "Weight", 0.0)
                # DISC: col2(Int1)=wave 被Zemax强制为0, col3(Int2)=field number!
                # 经诊断: col4(Hx)=Integer类型+无法写, col5(Hy)=DoubleValue read_back=inf(失败)
                # 结论: DISC 通过 col3(Int2)=field_idx 指定视场
                # col3 write 已确认有效(read_back=field_idx ✓)
                try:
                    _dc3 = row.GetOperandCell(3)
                    if _dc3 is not None:
                        _dc3.IntegerValue = field_idx
                except Exception:
                    pass
                added.append(("DISC", field_idx, _safe(mfe, "NumberOfOperands", 0)))

        # DIMX (最大畸变，wave=primary)
        dimx_row = None
        if type_val_dimx is not None:
            pos = _safe(mfe, "NumberOfOperands", 0) + 1
            row = None
            try:
                row = mfe.InsertNewOperandAt(pos)
            except Exception:
                try:
                    row = mfe.AddOperand()
                except Exception:
                    pass
            if row is not None:
                _set_row_operand_type(row, type_val_dimx)
                row = _refetch_last_row(mfe) or row
                _safe_set_attr(row, "Weight", 0.0)
                _set_operand_int_param(row, 1, primary_wave_idx)
                dimx_row = _safe(mfe, "NumberOfOperands", 0)

        try:
            mfe.CalculateMeritFunction()
        except Exception:
            pass

        # 读取 DISC
        samples = []
        seen_fields = set()
        for op_name, field_idx, rnum in added:
            if field_idx in seen_fields:
                continue
            seen_fields.add(field_idx)
            val = None
            try:
                val = _safe(mfe.GetOperandAt(rnum), "Value", None)
            except Exception:
                pass
            # 获取该视场的实际坐标
            f_obj = sys_data.Fields.GetField(field_idx)
            _, fy, _ = self.conn.get_field_data(f_obj)
            samples.append({
                "field": field_idx,
                "field_y": fy,
                "distortion_pct": round(val, 5) if val is not None else None,
            })

        dimx_val = None
        if dimx_row is not None:
            try:
                dimx_val = _safe(mfe.GetOperandAt(dimx_row), "Value", None)
            except Exception:
                pass

        # 清除
        all_rows = [r for _, _, r in added] + ([dimx_row] if dimx_row else [])
        for rnum in sorted(set(all_rows), reverse=True):
            try:
                mfe.DeleteOperandAt(rnum)
            except Exception:
                try:
                    mfe.RemoveOperandAt(rnum)
                except Exception:
                    pass

        abs_vals = [s["distortion_pct"] for s in samples if s["distortion_pct"] is not None]
        max_abs_dist = round(max(abs(v) for v in abs_vals), 5) if abs_vals else None

        result = {
            "max_distortion_pct": dimx_val if dimx_val is not None else max_abs_dist,
            "samples": samples,
            "guidelines": {
                "visual_instrument": "< 5%",
                "microscope": "< 1%",
                "measurement_instrument": "< 0.1%",
            },
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_mtf(self, frequency: float, wave: int = 0) -> str:
        """获取指定空间频率处各视场的 MTF 值 (切向/弧矢)，并与衍射极限比较。

        操作数:
          MTFT(Int1=wave, Int2=field, Int3/Param3=freq_in_lp_mm) → 切向 MTF
          MTHS(Int1=wave, Int2=field, Int3=freq) → 弧矢 MTF

        注意：Zemax 中 MTFT/MTHS 的频率参数单位为 cycles/mm，
        Param3 通常用 GetOperandCell(col=4) 设置浮点数。
        """
        mfe = self.conn.mfe
        sys_data = self.conn.system_data
        num_fields = sys_data.Fields.NumberOfFields
        num_waves = sys_data.Wavelengths.NumberOfWavelengths

        # 主波长
        primary_wave_idx = (num_waves + 1) // 2
        primary_wave_um = 0.5876
        try:
            w_obj = sys_data.Wavelengths.GetWavelength(primary_wave_idx)
            primary_wave_um, _ = self.conn.get_wavelength_data(w_obj)
        except Exception:
            pass

        wave_param = wave  # 0=多色

        type_val_mtft = _resolve_operand_type("MTFT")
        type_val_mths = _resolve_operand_type("MTHS")

        if type_val_mtft is None and type_val_mths is None:
            return json.dumps({"error": "当前 Zemax 版本不支持 MTFT/MTHS 操作数"}, ensure_ascii=False)

        added = []  # (label, field_idx, row_num)

        def _add_mtf_row(type_val, label, field_idx):
            pos = _safe(mfe, "NumberOfOperands", 0) + 1
            row = None
            try:
                row = mfe.InsertNewOperandAt(pos)
            except Exception:
                try:
                    row = mfe.AddOperand()
                except Exception:
                    return
            if row is None:
                return
            _set_row_operand_type(row, type_val)
            # ChangeType 后重新获取引用
            row = _refetch_last_row(mfe) or row
            _safe_set_attr(row, "Weight", 0.0)
            _safe_set_attr(row, "Target", 0.0)
            # col2=Int1=wave: Zemax 最小值=1, 0 会被重置为 1
            _wave_actual = max(1, wave_param) if wave_param > 0 else primary_wave_idx
            _set_operand_int_param(row, 1, _wave_actual)   # col2=wave
            _set_operand_int_param(row, 2, field_idx)       # col3=field ✓
            # col4=Param3=sampling (DataType=Integer, 合法范围 1-5)
            # col5=Param4=频率 (DataType=Double, 但 DoubleValue read_back=inf → 用 Value string)
            try:
                _fc4 = row.GetOperandCell(4)
                if _fc4 is not None:
                    _fc4.IntegerValue = 3   # sampling=3 (中等采样)
            except Exception:
                pass
            # 频率写入 col5: 必须用 Value(string)，DoubleValue 会返回 inf (虚假成功)
            try:
                _fc5 = row.GetOperandCell(5)
                if _fc5 is not None:
                    _fc5.Value = str(float(frequency))
            except Exception as _e5:
                # 最后尝试 DoubleValue
                try:
                    _fc5b = row.GetOperandCell(5)
                    if _fc5b is not None:
                        _fc5b.DoubleValue = float(frequency)
                except Exception:
                    pass
            added.append((label, field_idx, _safe(mfe, "NumberOfOperands", 0)))

        for fi in range(1, num_fields + 1):
            if type_val_mtft is not None:
                _add_mtf_row(type_val_mtft, "T", fi)
            if type_val_mths is not None:
                _add_mtf_row(type_val_mths, "S", fi)

        try:
            mfe.CalculateMeritFunction()
        except Exception:
            pass

        # 读取
        raw = {}
        for label, fi, rnum in added:
            key = (fi, label)
            try:
                raw[key] = _safe(mfe.GetOperandAt(rnum), "Value", None)
            except Exception:
                raw[key] = None

        # 清除
        all_rows = [r for _, _, r in added]
        for rnum in sorted(set(all_rows), reverse=True):
            try:
                mfe.DeleteOperandAt(rnum)
            except Exception:
                try:
                    mfe.RemoveOperandAt(rnum)
                except Exception:
                    pass

        # 理论衍射极限 MTF（单色，使用主波长）
        # 截止频率 f_c = 2*NA / λ (cycles/mm)
        image_na = None
        try:
            type_val_isna = _resolve_operand_type("ISNA")
            if type_val_isna is not None:
                pos = _safe(mfe, "NumberOfOperands", 0) + 1
                row = None
                try:
                    row = mfe.InsertNewOperandAt(pos)
                except Exception:
                    try:
                        row = mfe.AddOperand()
                    except Exception:
                        pass
                if row is not None:
                    _set_row_operand_type(row, type_val_isna)
                    _safe_set_attr(row, "Weight", 0.0)
                    mfe.CalculateMeritFunction()
                    isna_rnum = _safe(mfe, "NumberOfOperands", 0)
                    image_na = _safe(mfe.GetOperandAt(isna_rnum), "Value", None)
                    try:
                        mfe.DeleteOperandAt(isna_rnum)
                    except Exception:
                        try:
                            mfe.RemoveOperandAt(isna_rnum)
                        except Exception:
                            pass
        except Exception:
            pass

        cutoff_freq = None
        diffraction_limit_mtf = None
        if image_na and image_na > 0 and primary_wave_um:
            cutoff_freq = round(2 * image_na / (primary_wave_um * 1e-3), 1)  # λ in mm
            # 圆孔 OTF: MTF = (2/π) * [arccos(s) - s*sqrt(1-s²)], s = f/f_c
            s = frequency / cutoff_freq if cutoff_freq > 0 else 1.0
            if s >= 1.0:
                diffraction_limit_mtf = 0.0
            else:
                import math
                diffraction_limit_mtf = round((2 / math.pi) * (math.acos(s) - s * math.sqrt(1 - s ** 2)), 4)

        # 组装输出
        fields_data = []
        for fi in range(1, num_fields + 1):
            f_obj = sys_data.Fields.GetField(fi)
            _, fy, _ = self.conn.get_field_data(f_obj)
            entry = {
                "field": fi,
                "field_y": fy,
                "mtf_tangential": round(raw.get((fi, "T"), None) or 0, 4) if raw.get((fi, "T")) is not None else None,
                "mtf_sagittal": round(raw.get((fi, "S"), None) or 0, 4) if raw.get((fi, "S")) is not None else None,
            }
            if diffraction_limit_mtf is not None:
                entry["vs_diffraction_limit"] = {
                    "T": round(entry["mtf_tangential"] / diffraction_limit_mtf, 3) if entry["mtf_tangential"] is not None and diffraction_limit_mtf > 0 else None,
                    "S": round(entry["mtf_sagittal"] / diffraction_limit_mtf, 3) if entry["mtf_sagittal"] is not None and diffraction_limit_mtf > 0 else None,
                }
            fields_data.append(entry)

        result = {
            "frequency_cycles_per_mm": frequency,
            "image_na": image_na,
            "cutoff_frequency": cutoff_freq,
            "diffraction_limit_mtf": diffraction_limit_mtf,
            "fields": fields_data,
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_mtf_curve(self, num_points: int = 5, max_frequency: float = 0, wave: int = 0) -> str:
        """在多个空间频率点计算 MTF，返回完整曲线数据以及衍射极限理论曲线用于对比。"""
        import math
        mfe = self.conn.mfe
        sys_data = self.conn.system_data
        num_fields = sys_data.Fields.NumberOfFields
        num_waves = sys_data.Wavelengths.NumberOfWavelengths

        primary_wave_idx = (num_waves + 1) // 2
        primary_wave_um = 0.5876
        try:
            w_obj = sys_data.Wavelengths.GetWavelength(primary_wave_idx)
            primary_wave_um, _ = self.conn.get_wavelength_data(w_obj)
        except Exception:
            pass

        # 先获取 ISNA 以确定截止频率
        image_na = None
        type_val_isna = _resolve_operand_type("ISNA")
        if type_val_isna is not None:
            pos = _safe(mfe, "NumberOfOperands", 0) + 1
            row = None
            try:
                row = mfe.InsertNewOperandAt(pos)
            except Exception:
                try:
                    row = mfe.AddOperand()
                except Exception:
                    pass
            if row is not None:
                _set_row_operand_type(row, type_val_isna)
                _safe_set_attr(row, "Weight", 0.0)
                mfe.CalculateMeritFunction()
                isna_rnum = _safe(mfe, "NumberOfOperands", 0)
                image_na = _safe(mfe.GetOperandAt(isna_rnum), "Value", None)
                try:
                    mfe.DeleteOperandAt(isna_rnum)
                except Exception:
                    try:
                        mfe.RemoveOperandAt(isna_rnum)
                    except Exception:
                        pass

        cutoff_freq = None
        if image_na and image_na > 0 and primary_wave_um:
            cutoff_freq = round(2 * image_na / (primary_wave_um * 1e-3), 1)

        # 确定频率范围
        num_points = max(3, min(10, num_points))
        if max_frequency <= 0:
            if cutoff_freq:
                max_frequency = cutoff_freq
            else:
                max_frequency = 100.0
        frequencies = [round(max_frequency * i / (num_points - 1), 2) for i in range(1, num_points)]
        # 首点从 1/num_points 开始，避免 0 频率无意义
        # 末点取截止频率 * 0.95（或 max_frequency）
        if cutoff_freq and max_frequency >= cutoff_freq:
            frequencies[-1] = round(cutoff_freq * 0.95, 2)

        type_val_mtft = _resolve_operand_type("MTFT")
        type_val_mths = _resolve_operand_type("MTHS")

        if type_val_mtft is None and type_val_mths is None:
            return json.dumps({"error": "当前 Zemax 版本不支持 MTFT/MTHS 操作数"}, ensure_ascii=False)

        wave_param = max(1, wave) if wave > 0 else primary_wave_idx

        # 逐频率点调用 get_mtf 逻辑（重用核心逻辑，避免代码重复）
        curve_data = []
        for freq in frequencies:
            # 衍射极限理论值
            dl_mtf = None
            if cutoff_freq and cutoff_freq > 0:
                s = freq / cutoff_freq
                if s >= 1.0:
                    dl_mtf = 0.0
                else:
                    dl_mtf = round((2 / math.pi) * (math.acos(s) - s * math.sqrt(1 - s ** 2)), 4)

            # 添加每个视场的 MTFT + MTHS
            added = []

            def _add_row(type_val, label, fi):
                pos = _safe(mfe, "NumberOfOperands", 0) + 1
                row = None
                try:
                    row = mfe.InsertNewOperandAt(pos)
                except Exception:
                    try:
                        row = mfe.AddOperand()
                    except Exception:
                        return
                if row is None:
                    return
                _set_row_operand_type(row, type_val)
                row = _refetch_last_row(mfe) or row
                _safe_set_attr(row, "Weight", 0.0)
                _safe_set_attr(row, "Target", 0.0)
                _set_operand_int_param(row, 1, wave_param)
                _set_operand_int_param(row, 2, fi)
                try:
                    _fc4 = row.GetOperandCell(4)
                    if _fc4 is not None:
                        _fc4.IntegerValue = 3
                except Exception:
                    pass
                try:
                    _fc5 = row.GetOperandCell(5)
                    if _fc5 is not None:
                        _fc5.Value = str(float(freq))
                except Exception:
                    pass
                added.append((label, fi, _safe(mfe, "NumberOfOperands", 0)))

            for fi in range(1, num_fields + 1):
                if type_val_mtft is not None:
                    _add_row(type_val_mtft, "T", fi)
                if type_val_mths is not None:
                    _add_row(type_val_mths, "S", fi)

            try:
                mfe.CalculateMeritFunction()
            except Exception:
                pass

            raw = {}
            for label, fi, rnum in added:
                try:
                    raw[(fi, label)] = _safe(mfe.GetOperandAt(rnum), "Value", None)
                except Exception:
                    raw[(fi, label)] = None

            all_rows = [r for _, _, r in added]
            for rnum in sorted(set(all_rows), reverse=True):
                try:
                    mfe.DeleteOperandAt(rnum)
                except Exception:
                    try:
                        mfe.RemoveOperandAt(rnum)
                    except Exception:
                        pass

            fields_at_freq = []
            for fi in range(1, num_fields + 1):
                f_obj = sys_data.Fields.GetField(fi)
                _, fy, _ = self.conn.get_field_data(f_obj)
                entry = {
                    "field": fi,
                    "field_y": fy,
                    "T": round(raw.get((fi, "T")) or 0, 4) if raw.get((fi, "T")) is not None else None,
                    "S": round(raw.get((fi, "S")) or 0, 4) if raw.get((fi, "S")) is not None else None,
                }
                if dl_mtf is not None and dl_mtf > 0:
                    entry["T_vs_DL"] = round((entry["T"] or 0) / dl_mtf, 3)
                    entry["S_vs_DL"] = round((entry["S"] or 0) / dl_mtf, 3)
                fields_at_freq.append(entry)

            curve_data.append({
                "frequency": freq,
                "diffraction_limit": dl_mtf,
                "fields": fields_at_freq,
            })

        # 汇总：找出最差视场（全频率平均 T/S 最低）
        worst_field = None
        min_avg = 1.0
        for fi in range(1, num_fields + 1):
            vals = []
            for pt in curve_data:
                for fe in pt["fields"]:
                    if fe["field"] == fi:
                        if fe["T"] is not None:
                            vals.append(fe["T"])
                        if fe["S"] is not None:
                            vals.append(fe["S"])
            if vals:
                avg = sum(vals) / len(vals)
                if avg < min_avg:
                    min_avg = avg
                    worst_field = fi

        result = {
            "image_na": image_na,
            "cutoff_frequency": cutoff_freq,
            "primary_wavelength_um": primary_wave_um,
            "num_fields": num_fields,
            "worst_field": worst_field,
            "curve": curve_data,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    def check_manufacturability(self) -> str:
        """对当前系统每个透镜进行可制造性检查：边缘厚度、CT/ET比值、弯曲因子、最小曲率半径等。"""
        import math
        lde = self.conn.lde
        num_surfs = lde.NumberOfSurfaces  # 包含物面(0)和像面(last)
        last_surf = num_surfs - 1

        # 读取所有表面数据
        surfaces = []
        for i in range(num_surfs):
            s = lde.GetSurfaceAt(i)
            r = _safe(s, "Radius", 1e18)
            t = _safe(s, "Thickness", 0.0)
            mat = _safe(s, "Material", "") or ""
            sd = _safe(s, "SemiDiameter", 0.0) or 0.0
            surfaces.append({
                "surf": i,
                "radius": r if r is not None else 1e18,
                "thickness": t if t is not None else 0.0,
                "material": mat.strip(),
                "semi_diameter": abs(sd),
            })

        # 识别透镜元件：连续材料非空表面组
        # 一个透镜组 = 从第一个有材料的面到该组最后一个面（材料变为空气）
        lenses = []
        i = 1  # 跳过物面
        while i < last_surf:
            s = surfaces[i]
            if s["material"] and s["material"].upper() not in ("", "MIRROR"):
                # 开始一个透镜元件（可能是胶合组）
                group_surfs = [i]
                j = i + 1
                while j < last_surf and surfaces[j]["material"] and surfaces[j]["material"].upper() not in ("", "MIRROR"):
                    group_surfs.append(j)
                    j += 1
                # 最后一个表面是出射面（无材料）
                exit_surf = j if j < last_surf else j
                group_surfs.append(exit_surf)  # 出射面
                lenses.append(group_surfs)
                i = j + 1
            else:
                i += 1

        warnings = []
        elements = []

        for group in lenses:
            entry_surf_idx = group[0]
            exit_surf_idx = group[-1]
            entry = surfaces[entry_surf_idx]
            exit_ = surfaces[exit_surf_idx]

            R1 = entry["radius"]
            R2 = exit_["radius"]
            # 半口径取组内最大
            sd = max(surfaces[k]["semi_diameter"] for k in group)
            if sd == 0:
                sd = 1.0

            # 中心厚度 = 组内所有材料面的厚度之和
            ct = sum(surfaces[k]["thickness"] for k in group[:-1])

            # sag 计算：sag = R - sqrt(R² - h²)，h = semi_diameter
            def sag(R, h):
                if abs(R) > 1e15:  # 平面
                    return 0.0
                R2_minus_h2 = R ** 2 - h ** 2
                if R2_minus_h2 < 0:
                    return abs(R)  # 超出边缘（非物理），保守估计
                return R - math.copysign(math.sqrt(R2_minus_h2), R)

            sag1 = sag(R1, sd)
            sag2 = sag(R2, sd)
            # ET = CT - sag(入射面) + sag(出射面)
            # 注意符号：Zemax 定义下入射面正 sag 使边缘变薄，出射面正 sag 使边缘变厚
            et = ct - sag1 + sag2

            # 弯曲因子 B = (R2+R1)/(R2-R1)，平面令 R=∞→1e18
            R1_eff = R1 if abs(R1) < 1e15 else 1e18
            R2_eff = R2 if abs(R2) < 1e15 else 1e18
            try:
                B = (R2_eff + R1_eff) / (R2_eff - R1_eff) if abs(R2_eff - R1_eff) > 1e-6 else 999.0
            except Exception:
                B = None

            # 最小有效曲率半径
            min_r = min(
                (abs(surfaces[k]["radius"]) for k in group if abs(surfaces[k]["radius"]) < 1e15),
                default=None
            )

            # CT/ET 比值
            ct_et_ratio = round(ct / et, 3) if et != 0 else None
            # 半口径/CT 比（细长比）
            sd_ct_ratio = round(sd / ct, 3) if ct > 0 else None

            issues = []
            severity = "pass"

            if et < 0.3:
                issues.append(f"⚠️ 边缘厚度 ET={et:.3f}mm < 0.3mm，极薄无法加工")
                severity = "fail"
            elif et < 1.0:
                issues.append(f"⚠️ 边缘厚度 ET={et:.3f}mm < 1.0mm，装配风险")
                if severity != "fail":
                    severity = "warn"

            if ct < 1.0:
                issues.append(f"⚠️ 中心厚度 CT={ct:.3f}mm < 1.0mm，过薄")
                if severity != "fail":
                    severity = "warn"

            if ct_et_ratio is not None and ct_et_ratio > 10:
                issues.append(f"⚠️ CT/ET={ct_et_ratio:.1f}，正透镜边缘过薄，镀膜困难")
                if severity != "fail":
                    severity = "warn"
            if ct_et_ratio is not None and ct_et_ratio < 0.1:
                issues.append(f"⚠️ CT/ET={ct_et_ratio:.3f}，负透镜中心过薄")
                if severity != "fail":
                    severity = "warn"

            if min_r is not None and min_r < 3.0:
                issues.append(f"⚠️ 最小曲率半径 R={min_r:.2f}mm < 3mm，难以抛光")
                if severity != "fail":
                    severity = "warn"

            if sd_ct_ratio is not None and sd_ct_ratio > 8:
                issues.append(f"⚠️ 半口径/CT={sd_ct_ratio:.1f}，透镜过于扁平，加工变形风险")
                if severity != "fail":
                    severity = "warn"

            if B is not None and abs(B) > 5:
                issues.append(f"⚠️ 弯曲因子 B={B:.2f}，极端弯月形，慧差校正困难")
                if severity != "fail":
                    severity = "warn"

            element = {
                "surfs": group,
                "R1": round(R1, 4) if abs(R1) < 1e15 else "∞",
                "R2": round(R2, 4) if abs(R2) < 1e15 else "∞",
                "center_thickness_mm": round(ct, 4),
                "edge_thickness_mm": round(et, 4),
                "semi_diameter_mm": round(sd, 4),
                "ct_et_ratio": ct_et_ratio,
                "sd_ct_ratio": sd_ct_ratio,
                "bend_factor_B": round(B, 3) if B is not None else None,
                "min_radius_mm": round(min_r, 4) if min_r is not None else None,
                "severity": severity,
                "issues": issues,
            }
            elements.append(element)
            warnings.extend(issues)

        overall = "pass"
        if any(e["severity"] == "fail" for e in elements):
            overall = "fail"
        elif any(e["severity"] == "warn" for e in elements):
            overall = "warn"

        result = {
            "overall": overall,
            "num_elements": len(elements),
            "elements": elements,
            "summary": warnings if warnings else ["✅ 所有透镜元件通过可制造性检查"],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ---- 玻璃库管理 ----
    def get_glass_catalogs(self, catalog: str = None) -> str:
        """获取玻璃库信息：当前使用的目录、可用目录、指定目录中的材料。"""
        mat_cat = self.conn.system_data.MaterialCatalogs

        in_use = list(_safe(mat_cat, "GetCatalogsInUse", ()) or ())
        available = list(_safe(mat_cat, "GetAvailableCatalogs", ()) or ())

        result = {
            "catalogs_in_use": in_use,
            "available_catalogs": available,
        }

        if catalog:
            materials = list(mat_cat.GetMaterialsInCatalog(catalog) or ())
            result["query_catalog"] = catalog
            result["materials"] = materials
            result["material_count"] = len(materials)

        return json.dumps(result, ensure_ascii=False, indent=2)

    def set_glass_catalogs(self, add: list = None, remove: list = None) -> str:
        """添加或移除玻璃库目录。"""
        mat_cat = self.conn.system_data.MaterialCatalogs

        results = {"added": [], "removed": [], "errors": []}

        if remove:
            for cat_name in remove:
                try:
                    ok = mat_cat.RemoveCatalog(cat_name)
                    if ok:
                        results["removed"].append(cat_name)
                    else:
                        results["errors"].append(f"移除 '{cat_name}' 失败 (可能不在使用列表中)")
                except Exception as e:
                    results["errors"].append(f"移除 '{cat_name}' 异常: {e}")

        if add:
            for cat_name in add:
                try:
                    ok = mat_cat.AddCatalog(cat_name)
                    if ok:
                        results["added"].append(cat_name)
                    else:
                        results["errors"].append(f"添加 '{cat_name}' 失败 (可能名称不正确或已在使用)")
                except Exception as e:
                    results["errors"].append(f"添加 '{cat_name}' 异常: {e}")

        # 返回更新后的状态
        results["catalogs_in_use"] = list(_safe(mat_cat, "GetCatalogsInUse", ()) or ())
        results["ok"] = len(results["errors"]) == 0

        return json.dumps(results, ensure_ascii=False, indent=2)

    # ---- UI 刷新与布局 ----
    def update_ui(self) -> str:
        """刷新 OpticStudio GUI，并刷新所有已打开的分析窗口。"""
        system = self.conn.system

        # 1. UpdateStatus 刷新主窗口 (LDE / 编辑器)
        status_msg = None
        try:
            status_msg = system.UpdateStatus()
        except Exception as e:
            status_msg = f"UpdateStatus 异常: {e}"

        # 2. 遍历已打开的分析窗口并刷新
        refreshed = 0
        try:
            analyses = system.Analyses
            n = _safe(analyses, "NumberOfAnalyses", 0)
            for i in range(1, n + 1):
                try:
                    a = analyses.Get_AnalysisAtIndex(i)
                    if a is not None:
                        a.ApplyAndWaitForCompletion()
                        refreshed += 1
                except Exception:
                    continue
        except Exception:
            pass

        return json.dumps(
            {"ok": True, "status": status_msg, "analyses_refreshed": refreshed},
            ensure_ascii=False,
        )

    def open_layout(self, layout_type: str = "2D", export_path: str = None) -> str:
        """在 OpticStudio GUI 中打开 2D/3D 布局图窗口。"""
        system = self.conn.system

        # AnalysisIDM 枚举值
        layout_map = {"2D": 56, "3D": 57}  # Draw2D=56, Draw3D=57
        analysis_type = layout_map.get(layout_type.upper(), 56)

        analyses = system.Analyses
        analysis = None
        try:
            analysis = analyses.New_Analysis(analysis_type)
        except Exception as e:
            return json.dumps(
                {"error": f"无法打开 {layout_type} 布局窗口: {e}"},
                ensure_ascii=False,
            )

        if analysis is None:
            return json.dumps(
                {"error": f"无法打开 {layout_type} 布局窗口 (返回 None)"},
                ensure_ascii=False,
            )

        # 等待计算完成
        try:
            analysis.ApplyAndWaitForCompletion()
        except Exception:
            try:
                analysis.WaitForCompletion()
            except Exception:
                pass

        result = {
            "ok": True,
            "layout_type": layout_type,
            "message": f"{layout_type} 布局图已在 OpticStudio GUI 中打开",
        }

        # 可选：导出到文件
        if export_path:
            try:
                analysis.ToFile(export_path, False, False)
                result["exported_to"] = export_path
            except Exception as e:
                result["export_error"] = str(e)

        # 注意：不要 Close()，让窗口保留在 GUI 中供用户查看

        return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
#  辅助
# ---------------------------------------------------------------------------

def _refetch_last_row(mfe):
    """ChangeType() 调用可能使原 row COM 引用失效（内部创建新对象），
    通过 NumberOfOperands 行号重新获取最新有效引用。
    在 _set_row_operand_type 后立即调用，确保后续参数写入有效。
    """
    try:
        num = _safe(mfe, "NumberOfOperands", 0)
        return mfe.GetOperandAt(num)
    except Exception:
        return None


def _safe(obj, attr, default):
    """安全获取 COM 对象属性 (多策略: 直接 → prop_map → 模糊匹配)."""
    # 策略 1: 直接 getattr
    try:
        return getattr(obj, attr)
    except Exception:
        pass
    # 策略 2: 从 _prop_map_get_ 字典查找 (参考 PyZOS)
    prop_map = getattr(obj, "_prop_map_get_", None)
    if prop_map:
        # 精确匹配
        if attr in prop_map:
            try:
                return getattr(obj, attr)
            except Exception:
                pass
        # 模糊匹配 (大小写不敏感)
        for key in prop_map:
            if key.lower() == attr.lower():
                try:
                    return getattr(obj, key)
                except Exception:
                    pass
    return default


def _cast_to_system_tool(tool_obj):
    """将 ILocalOptimization / IQuickFocus 等 COM 对象转型为 ISystemTool.

    参考 PyZOS inheritance_dict:
        ILocalOptimization -> ISystemTool
        IQuickFocus -> ISystemTool
    RunAndWaitForCompletion() 和 Close() 定义在 ISystemTool 基类上,
    早期绑定生成的派生类包装器不包含基类方法, 必须 CastTo。
    """
    from win32com.client import CastTo
    try:
        return CastTo(tool_obj, "ISystemTool")
    except Exception:
        # 如果 CastTo 失败 (如某些版本接口名不同), 尝试直接返回
        # 在后期绑定场景下对象可能已经有这些方法
        return tool_obj


def _safe_set_attr(obj, attr, value):
    """安全设置 COM 对象属性, 静默忽略失败. 返回是否成功."""
    try:
        setattr(obj, attr, value)
        return True
    except Exception:
        return False


# 只读工具集 — 不触发自动 UI 刷新
_READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "get_system_info",
    "get_merit_function",
    "get_operands",
    "get_first_order_data",
    "get_image_quality",
    "get_aberrations",
    "get_distortion",
    "get_mtf",
    "get_mtf_curve",
    "check_manufacturability",
    "get_glass_catalogs",
    "update_ui",      # 本身就是刷新工具，无需再次触发
    "open_layout",    # 打开窗口后自身已做 ApplyAndWaitForCompletion
})


def _is_com_disconnect_error(err_str: str) -> bool:
    """判断异常是否属于 COM 连接断开类错误.

    注意: NoneType 属性错误不是连接断开, 而是 COM 方法返回了 None (如工具无法打开).
    """
    err_lower = err_str.lower()
    # 排除 NoneType 错误 — 这不是连接断开
    if "'nonetype'" in err_lower:
        return False
    # 真正的 COM 断连指标
    indicators = [
        "rpc", "disconnected", "call was rejected",
        "server threw an exception", "com_error",
        "0x800706ba",   # RPC server unavailable
        "0x80010108",   # Object invoked has disconnected
        "0x800706be",   # Remote procedure call failed
        "0x80010105",   # Server threw an exception
        "0x800401fd",   # ServerNotAvailable
    ]
    return any(ind in err_lower for ind in indicators)


def _resolve_operand_type(operand_name):
    """将操作数类型名 (如 'EFFL') 解析为 COM 枚举整数值.

    ZOS-API COM 常量注册在 win32com.client.constants 中,
    命名可能为 EFFL / MeritOperandType_EFFL 等。
    """
    from win32com.client import constants

    name = operand_name.upper().strip()

    # 策略 1: 直接常量访问
    for pattern in [name, f"MeritOperandType_{name}"]:
        try:
            return getattr(constants, pattern)
        except AttributeError:
            continue

    # 策略 2: 搜索常量字典
    try:
        const_dicts = getattr(constants, "__dicts__", None)
        if const_dicts:
            for d in const_dicts:
                for key, val in d.items():
                    key_upper = key.upper()
                    if key_upper == name or key_upper.endswith(f"_{name}"):
                        return val
    except Exception:
        pass

    return None


def _set_row_operand_type(row, type_val):
    """在 MFE 行上设置操作数类型 (多策略).

    ZOS-API 不同版本的接口存在差异:
    - 新版: row.GetOperandTypeSettings(enum) → settings → row.ChangeType(settings)
    - 旧版: row.ChangeType(enum) 或 row.Type = enum
    """
    # 策略 1: GetOperandTypeSettings + ChangeType
    try:
        settings = row.GetOperandTypeSettings(type_val)
        row.ChangeType(settings)
        return True
    except Exception:
        pass
    # 策略 2: 直接 ChangeType(enum)
    try:
        row.ChangeType(type_val)
        return True
    except Exception:
        pass
    # 策略 3: 设置 Type 属性
    if _safe_set_attr(row, "Type", type_val):
        return True
    return False


def _set_operand_int_param(row, param_num, value):
    """设置 MFE 行的整数参数 (Param1/Param2/...).

    IMFERow (早期绑定) 的 _prop_map_put_ 里没有 Param1/Param2,
    直接 setattr 只会添加 Python 实例属性而不触发 COM 调用 (静默假成功)。
    必须用 GetOperandCell(col).IntegerValue 作为首选路径。
    MeritColumn 枚举: Param1=col2, Param2=col3, Param3=col4, ...
    """
    col_idx = param_num + 1  # Param1→col2, Param2→col3, ...
    # 策略 1: GetOperandCell (IMFERow 的正确路径)
    try:
        cell = row.GetOperandCell(col_idx)
        if cell is not None:
            # 先读回确认写入有效
            cell.IntegerValue = int(value)
            return True
    except Exception:
        pass
    # 策略 2: 直接属性 Param1, Param2, ... (IMCERow 等其他接口)
    attr = f"Param{param_num}"
    try:
        # 只对有 _prop_map_put_ 记录的真实 COM 属性才写入
        prop_map = getattr(row.__class__, "_prop_map_put_", {})
        if attr in prop_map:
            setattr(row, attr, int(value))
            return True
    except Exception:
        pass
    # 策略 3: GetCellAt
    try:
        cell = row.GetCellAt(col_idx)
        if cell is not None:
            try:
                cell.IntegerValue = int(value)
            except AttributeError:
                cell.Value = str(value)
            return True
    except Exception:
        pass
    return False


def _set_operand_double_param(row, param_num, value):
    """设置 MFE 行的浮点参数 (Hx/Hy/Px/Py/frequency 等).

    MeritColumn 枚举: Param1=col2, Param2=col3, Param3(Hx)=col4, Param4(Hy)=col5, ...
    使用 GetOperandCell(col).DoubleValue 写入。
    """
    col_idx = param_num + 1
    # 策略 1: GetOperandCell.DoubleValue (首选)
    try:
        cell = row.GetOperandCell(col_idx)
        if cell is not None:
            cell.DoubleValue = float(value)
            return True
    except Exception as e:
        # 如果 DoubleValue 抛出 "Expected Double, got Integer" 等, 尝试字符串路径
        try:
            cell = row.GetOperandCell(col_idx)
            if cell is not None:
                cell.Value = str(float(value))
                return True
        except Exception:
            pass
    # 策略 2: GetCellAt.DoubleValue
    try:
        cell = row.GetCellAt(col_idx)
        if cell is not None:
            cell.DoubleValue = float(value)
            return True
    except Exception:
        pass
    return False
