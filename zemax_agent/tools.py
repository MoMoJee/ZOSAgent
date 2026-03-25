"""Zemax 工具定义与实现 — 供 AI Agent 调用."""

import json
import traceback

from zemax_connection import ZemaxConnection

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
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

        # 执行前检测连接状态
        if not self.conn.is_alive:
            print("\033[33m  [连接丢失] 正在尝试自动重连...\033[0m")
            if not self.conn.reconnect():
                return json.dumps(
                    {"error": "OpticStudio 连接已断开且无法自动重连。请在 Zemax 中重新打开 Interactive Extension，然后输入 reconnect 手动重连。"},
                    ensure_ascii=False,
                )
            print("\033[32m  [已重连] 继续执行工具...\033[0m")

        try:
            result = fn(**arguments)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            err_str = str(e)
            # 检测 COM 断连类异常，尝试重连后重试一次
            if _is_com_disconnect_error(err_str):
                print("\033[33m  [COM 异常] 连接可能已断开，尝试重连...\033[0m")
                if self.conn.reconnect():
                    try:
                        result = fn(**arguments)
                        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
                    except Exception as e2:
                        return json.dumps(
                            {"error": str(e2), "traceback": traceback.format_exc()},
                            ensure_ascii=False,
                        )
            return json.dumps(
                {"error": err_str, "traceback": traceback.format_exc()},
                ensure_ascii=False,
            )

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


# ---------------------------------------------------------------------------
#  辅助
# ---------------------------------------------------------------------------

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

    尝试多种访问路径: 直接属性 → GetOperandCell → GetCellAt.
    """
    # 策略 1: 直接属性 Param1, Param2, ...
    attr = f"Param{param_num}"
    if _safe_set_attr(row, attr, value):
        return True
    # 策略 2: GetOperandCell (col 2=Int1, col 3=Int2 in ZOS-API)
    col_idx = param_num + 1
    try:
        cell = row.GetOperandCell(col_idx)
        if cell is not None:
            cell.IntegerValue = value
            return True
    except Exception:
        pass
    # 策略 3: GetCellAt
    try:
        cell = row.GetCellAt(col_idx)
        if cell is not None:
            try:
                cell.IntegerValue = value
            except AttributeError:
                cell.Value = value
            return True
    except Exception:
        pass
    return False
