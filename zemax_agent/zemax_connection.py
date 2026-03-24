"""Zemax OpticStudio COM 连接管理 (兼容 2018 版)."""


class ZemaxConnection:
    """通过 COM 接口 (ZOS-API) 管理与 OpticStudio 的连接."""

    def __init__(self):
        self._connection = None
        self._app = None
        self._system = None
        self._constants = None

    def connect(self, mode="extension", instance=0):
        """连接到 OpticStudio.

        Args:
            mode: "extension" 连接到运行中的实例, "standalone" 启动新实例
            instance: Extension 实例编号 (默认 0)
        """
        from win32com.client import constants, gencache
        from win32com.client.gencache import EnsureDispatch

        # 注册 ZOS-API COM 类型库
        gencache.EnsureModule("{EA433010-2BAC-43C4-857C-7AEAC4A8CCE0}", 0, 1, 0)
        gencache.EnsureModule("{F66684D7-AAFE-4A62-9156-FF7A7853F764}", 0, 1, 0)

        self._connection = EnsureDispatch("ZOSAPI.ZOSAPI_Connection")
        if self._connection is None:
            raise ConnectionError("无法初始化 ZOSAPI COM 连接")

        if mode == "extension":
            self._app = self._connection.ConnectAsExtension(instance)
        elif mode == "standalone":
            self._app = self._connection.CreateNewApplication()
        else:
            raise ValueError(f"未知连接模式: {mode}")

        if self._app is None:
            raise ConnectionError(
                "无法连接到 OpticStudio。请确保:\n"
                "  1. OpticStudio 正在运行\n"
                "  2. 已点击 Programming > Interactive Extension"
            )

        if not self._app.IsValidLicenseForAPI:
            raise ConnectionError("当前许可证不支持 ZOS-API 使用")

        self._system = self._app.PrimarySystem
        if self._system is None:
            raise ConnectionError("无法获取主光学系统")

        self._constants = constants
        return True

    @property
    def app(self):
        return self._app

    @property
    def system(self):
        return self._system

    @property
    def constants(self):
        return self._constants

    @property
    def lde(self):
        """Lens Data Editor."""
        return self._system.LDE

    @property
    def mfe(self):
        """Merit Function Editor."""
        return self._system.MFE

    @property
    def system_data(self):
        return self._system.SystemData

    def disconnect(self):
        self._connection = None
        self._app = None
        self._system = None
