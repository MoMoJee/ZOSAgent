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
]


# ---------------------------------------------------------------------------
#  工具实现
# ---------------------------------------------------------------------------


class ZemaxToolkit:
    """封装所有 Zemax 工具的调用逻辑."""

    def __init__(self, conn: ZemaxConnection):
        self.conn = conn

    # ---- 分发 ----
    def dispatch(self, tool_name: str, arguments: dict) -> str:
        """根据工具名调用对应方法，返回 JSON 字符串结果."""
        fn = getattr(self, tool_name, None)
        if fn is None:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
        try:
            result = fn(**arguments)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps(
                {"error": str(e), "traceback": traceback.format_exc()},
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

        # 视场
        fields_info = []
        for i in range(1, sys_data.Fields.NumberOfFields + 1):
            f = sys_data.Fields.GetField(i)
            fields_info.append({"index": i, "x": f.X, "y": f.Y, "weight": f.Weight})

        # 波长
        wavelengths_info = []
        for i in range(1, sys_data.Wavelengths.NumberOfWavelengths + 1):
            w = sys_data.Wavelengths.GetWavelength(i)
            wavelengths_info.append({"index": i, "value_um": w.Value, "weight": w.Weight})

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

        # 设置第一个视场
        if fields:
            f0 = fields[0]
            first = flds.GetField(1)
            first.X = f0.get("x", 0.0)
            first.Y = f0.get("y", 0.0)
            first.Weight = f0.get("weight", 1.0)

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

        # 设置第一个波长
        w0 = wavelengths[0]
        first = wls.GetWavelength(1)
        first.Value = w0["value"]
        first.Weight = w0.get("weight", 1.0)

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
        tools = self.conn.system.Tools
        opt = tools.OpenLocalOptimization()

        # 算法
        if algorithm == "OD":
            try:
                opt.Algorithm = 1  # OrthogonalDescent
            except Exception:
                pass
        else:
            try:
                opt.Algorithm = 0  # DampedLeastSquares
            except Exception:
                pass

        # 循环次数
        cycles_map = {
            "Automatic": 0,
            "Fixed_1": 1,
            "Fixed_5": 5,
            "Fixed_10": 10,
            "Fixed_50": 50,
        }
        cycle_val = cycles_map.get(cycles, 0)
        if cycle_val == 0:
            try:
                opt.Cycles = -1  # Automatic
            except Exception:
                pass
        else:
            try:
                opt.NumberOfCycles = cycle_val
            except Exception:
                try:
                    opt.Cycles = cycle_val
                except Exception:
                    pass

        opt.RunAndWaitForCompletion()
        mfv = opt.CurrentMeritFunction
        opt.Close()

        return json.dumps(
            {"ok": True, "algorithm": algorithm, "cycles": cycles, "final_merit_function": mfv},
            ensure_ascii=False,
        )

    def quick_focus(self) -> str:
        tools = self.conn.system.Tools
        qf = tools.OpenQuickFocus()
        try:
            qf.Criterion = 0  # SpotSizeRadial
            qf.UseCentroid = True
        except Exception:
            pass
        qf.RunAndWaitForCompletion()
        qf.Close()
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


# ---------------------------------------------------------------------------
#  辅助
# ---------------------------------------------------------------------------

def _safe(obj, attr, default):
    """安全获取 COM 对象属性."""
    try:
        return getattr(obj, attr)
    except Exception:
        return default
