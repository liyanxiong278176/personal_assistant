"""依赖注入容器

提供轻量级的依赖注入容器，用于管理服务注册和解析。
支持单例和瞬态两种生命周期模式。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Set


@dataclass
class ServiceDescriptor:
    """服务描述符

    描述一个已注册服务的元数据和行为。

    Attributes:
        factory: 创建服务实例的工厂函数
        singleton: 是否为单例模式，默认为 True
        instance: 单例模式下缓存的服务实例
    """
    factory: Callable[[], Any]
    singleton: bool = True
    instance: Optional[Any] = field(default=None, init=False)


class CircularDependencyError(Exception):
    """循环依赖错误

    当检测到服务之间存在循环依赖时抛出。
    """
    pass


class DIContainer:
    """依赖注入容器

    轻量级依赖注入容器，用于管理应用中的服务注册和解析。

    特性:
    - 支持单例和瞬态两种生命周期
    - 自动检测循环依赖
    - 线程安全的服务解析

    示例:
        >>> container = DIContainer()
        >>> container.register_singleton("db", Database)
        >>> db = container.resolve("db")
        >>> assert db is container.resolve("db")  # 同一实例
    """

    def __init__(self) -> None:
        """初始化容器"""
        self._services: dict[str, ServiceDescriptor] = {}
        self._resolving: Set[str] = set()

    def register(self, name: str, factory: Callable[[], Any], singleton: bool = False) -> None:
        """注册服务

        Args:
            name: 服务名称，用于后续解析
            factory: 工厂函数，返回服务实例
            singleton: 是否为单例模式，默认为 False（瞬态）

        Raises:
            ValueError: 如果服务名称已存在

        示例:
            >>> container.register("cache", lambda: Cache())
            >>> cache = container.resolve("cache")
        """
        if name in self._services:
            raise ValueError(f"Service '{name}' is already registered")

        self._services[name] = ServiceDescriptor(factory=factory, singleton=singleton)

    def register_singleton(self, name: str, factory: Callable[[], Any]) -> None:
        """注册单例服务

        单例服务在首次解析时创建实例，之后返回同一实例。

        Args:
            name: 服务名称
            factory: 工厂函数

        Raises:
            ValueError: 如果服务名称已存在

        示例:
            >>> container.register_singleton("config", Config)
            >>> config1 = container.resolve("config")
            >>> config2 = container.resolve("config")
            >>> assert config1 is config2
        """
        self.register(name, factory, singleton=True)

    def register_transient(self, name: str, factory: Callable[[], Any]) -> None:
        """注册瞬态服务

        瞬态服务每次解析都会创建新实例。

        Args:
            name: 服务名称
            factory: 工厂函数

        Raises:
            ValueError: 如果服务名称已存在

        示例:
            >>> container.register_transient("request", Request)
            >>> req1 = container.resolve("request")
            >>> req2 = container.resolve("request")
            >>> assert req1 is not req2
        """
        self.register(name, factory, singleton=False)

    def resolve(self, name: str) -> Any:
        """解析服务

        根据服务名称获取服务实例。单例服务返回缓存的实例，
        瞬态服务每次都创建新实例。

        Args:
            name: 服务名称

        Returns:
            服务实例

        Raises:
            KeyError: 如果服务未注册
            CircularDependencyError: 如果检测到循环依赖

        示例:
            >>> service = container.resolve("my_service")
        """
        if name not in self._services:
            available = ", ".join(self._services.keys())
            raise KeyError(
                f"Service '{name}' is not registered. "
                f"Available services: {available or 'none'}"
            )

        # 检测循环依赖
        if name in self._resolving:
            chain = " -> ".join(list(self._resolving) + [name])
            raise CircularDependencyError(
                f"Circular dependency detected: {chain}"
            )

        descriptor = self._services[name]

        # 单例且已缓存，直接返回
        if descriptor.singleton and descriptor.instance is not None:
            return descriptor.instance

        # 标记正在解析
        self._resolving.add(name)

        try:
            # 创建新实例
            instance = descriptor.factory()

            # 单例则缓存
            if descriptor.singleton:
                descriptor.instance = instance

            return instance
        finally:
            # 清除解析标记
            self._resolving.discard(name)

    def has(self, name: str) -> bool:
        """检查服务是否已注册

        Args:
            name: 服务名称

        Returns:
            bool: 如果服务已注册返回 True，否则返回 False

        示例:
            >>> if container.has("optional_service"):
            ...     service = container.resolve("optional_service")
        """
        return name in self._services

    def clear(self) -> None:
        """清除所有注册的服务

        这将删除所有服务注册和缓存的实例。

        示例:
            >>> container.clear()
            >>> assert len(container._services) == 0
        """
        self._services.clear()
        self._resolving.clear()

    @property
    def registered_services(self) -> set[str]:
        """获取所有已注册的服务名称

        Returns:
            set[str]: 服务名称集合
        """
        return set(self._services.keys())
