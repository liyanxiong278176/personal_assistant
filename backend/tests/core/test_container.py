"""依赖注入容器测试"""

import pytest

from app.core.container import DIContainer, CircularDependencyError, ServiceDescriptor


class DummyService:
    """用于测试的简单服务"""

    def __init__(self):
        self.value = 42


class AnotherService:
    """另一个测试服务"""

    def __init__(self):
        self.name = "test"


class TestDIContainer:
    """DI容器测试类"""

    def test_container_initially_empty(self):
        """测试容器初始为空"""
        container = DIContainer()
        assert len(container.registered_services) == 0
        assert container.has("anything") is False

    def test_container_register_and_resolve(self):
        """测试注册和解析服务"""
        container = DIContainer()

        # 注册服务
        container.register("dummy", lambda: DummyService())

        # 验证服务已注册
        assert container.has("dummy") is True
        assert "dummy" in container.registered_services

        # 解析服务
        service = container.resolve("dummy")
        assert isinstance(service, DummyService)
        assert service.value == 42

    def test_container_resolve_unregistered_raises_key_error(self):
        """测试解析未注册的服务抛出 KeyError"""
        container = DIContainer()

        with pytest.raises(KeyError) as exc_info:
            container.resolve("nonexistent")

        assert "nonexistent" in str(exc_info.value)
        assert "is not registered" in str(exc_info.value)

    def test_container_key_error_includes_available_services(self):
        """测试 KeyError 包含可用服务列表"""
        container = DIContainer()
        container.register("service1", lambda: DummyService())
        container.register("service2", lambda: AnotherService())

        with pytest.raises(KeyError) as exc_info:
            container.resolve("missing")

        error_msg = str(exc_info.value)
        assert "service1" in error_msg
        assert "service2" in error_msg

    def test_container_has(self):
        """测试 has 方法"""
        container = DIContainer()

        assert container.has("anything") is False

        container.register("service", lambda: DummyService())
        assert container.has("service") is True
        assert container.has("Service") is False  # 大小写敏感

    def test_container_clear(self):
        """测试清除所有注册"""
        container = DIContainer()
        container.register("s1", lambda: DummyService())
        container.register("s2", lambda: AnotherService())

        assert len(container.registered_services) == 2

        container.clear()

        assert len(container.registered_services) == 0
        assert container.has("s1") is False
        assert container.has("s2") is False

    def test_container_singleton_returns_same_instance(self):
        """测试单例模式返回同一实例"""
        container = DIContainer()

        container.register_singleton("dummy", DummyService)

        instance1 = container.resolve("dummy")
        instance2 = container.resolve("dummy")

        assert instance1 is instance2
        assert instance1.value == 42

    def test_container_transient_creates_new_instance(self):
        """测试瞬态模式创建新实例"""
        container = DIContainer()

        container.register_transient("dummy", DummyService)

        instance1 = container.resolve("dummy")
        instance2 = container.resolve("dummy")

        assert instance1 is not instance2
        assert instance1.value == 42
        assert instance2.value == 42

    def test_container_register_with_singleton_false(self):
        """测试使用 register 方法注册瞬态服务"""
        container = DIContainer()

        container.register("dummy", lambda: DummyService(), singleton=False)

        instance1 = container.resolve("dummy")
        instance2 = container.resolve("dummy")

        assert instance1 is not instance2

    def test_container_register_with_singleton_true(self):
        """测试使用 register 方法注册单例服务"""
        container = DIContainer()

        container.register("dummy", lambda: DummyService(), singleton=True)

        instance1 = container.resolve("dummy")
        instance2 = container.resolve("dummy")

        assert instance1 is instance2

    def test_container_register_duplicate_raises_value_error(self):
        """测试注册重复服务名称抛出 ValueError"""
        container = DIContainer()

        container.register("service", lambda: DummyService())

        with pytest.raises(ValueError) as exc_info:
            container.register("service", lambda: AnotherService())

        assert "already registered" in str(exc_info.value)
        assert "service" in str(exc_info.value)

    def test_container_singleton_via_register_singleton(self):
        """测试 register_singleton 方法"""
        container = DIContainer()

        container.register_singleton("service", DummyService)

        instance1 = container.resolve("service")
        instance2 = container.resolve("service")

        assert instance1 is instance2

    def test_container_transient_via_register_transient(self):
        """测试 register_transient 方法"""
        container = DIContainer()

        container.register_transient("service", DummyService)

        instance1 = container.resolve("service")
        instance2 = container.resolve("service")

        assert instance1 is not instance2

    def test_container_factory_receives_no_arguments(self):
        """测试工厂函数不接受参数"""
        container = DIContainer()

        # 工厂函数不接受参数
        def factory():
            return "created"

        container.register("str_service", factory)
        assert container.resolve("str_service") == "created"

    def test_container_factory_can_use_lambda(self):
        """测试可以使用 lambda 作为工厂函数"""
        container = DIContainer()

        container.register("list_service", lambda: [])
        container.register("dict_service", lambda: {})

        assert container.resolve("list_service") == []
        assert container.resolve("dict_service") == {}

    def test_container_registered_services_property(self):
        """测试 registered_services 属性"""
        container = DIContainer()

        assert container.registered_services == set()

        container.register("s1", lambda: None)
        container.register("s2", lambda: None)
        container.register("s3", lambda: None)

        services = container.registered_services
        assert services == {"s1", "s2", "s3"}

    def test_container_circular_dependency_detection(self):
        """测试循环依赖检测"""
        container = DIContainer()

        # 创建循环依赖
        def create_a():
            # 在工厂函数中解析另一个服务
            b = container.resolve("b")
            return {"a": 1, "b_ref": b}

        def create_b():
            a = container.resolve("a")
            return {"b": 2, "a_ref": a}

        container.register("a", create_a)
        container.register("b", create_b)

        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve("a")

        error_msg = str(exc_info.value)
        assert "Circular dependency" in error_msg
        assert "a" in error_msg
        assert "b" in error_msg

    def test_container_self_circular_dependency(self):
        """测试自循环依赖检测"""
        container = DIContainer()

        def create_self():
            # 服务依赖自己
            return container.resolve("self")

        container.register("self", create_self)

        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve("self")

        assert "self" in str(exc_info.value)

    def test_container_no_false_positive_circular_dependency(self):
        """测试没有循环依赖时正常工作"""
        container = DIContainer()

        # 创建正常的依赖链：c -> b -> a
        def create_a():
            return "A"

        def create_b():
            a = container.resolve("a")
            return f"B({a})"

        def create_c():
            b = container.resolve("b")
            return f"C({b})"

        container.register("a", create_a)
        container.register("b", create_b)
        container.register("c", create_c)

        result = container.resolve("c")
        assert result == "C(B(A))"

    def test_container_multiple_independent_singletons(self):
        """测试多个独立的单例服务"""
        container = DIContainer()

        container.register_singleton("s1", DummyService)
        container.register_singleton("s2", AnotherService)

        s1_a = container.resolve("s1")
        s1_b = container.resolve("s1")
        s2_a = container.resolve("s2")
        s2_b = container.resolve("s2")

        # 同一服务返回相同实例
        assert s1_a is s1_b
        assert s2_a is s2_b

        # 不同服务返回不同实例
        assert s1_a is not s2_a
        assert isinstance(s1_a, DummyService)
        assert isinstance(s2_a, AnotherService)

    def test_container_factory_exception_propagates(self):
        """测试工厂函数异常会传播"""
        container = DIContainer()

        def failing_factory():
            raise RuntimeError("Factory failed")

        container.register("failing", failing_factory)

        with pytest.raises(RuntimeError, match="Factory failed"):
            container.resolve("failing")

    def test_container_state_after_factory_exception(self):
        """测试工厂函数异常后容器状态正常"""
        container = DIContainer()

        def failing_factory():
            raise ValueError("Error")

        container.register("failing", failing_factory)
        container.register("working", lambda: "ok")

        # 解析失败的服务
        with pytest.raises(ValueError):
            container.resolve("failing")

        # 容器状态应正常，其他服务仍可解析
        assert container.has("failing") is True
        assert container.has("working") is True
        assert container.resolve("working") == "ok"


class TestServiceDescriptor:
    """测试 ServiceDescriptor 数据类"""

    def test_service_descriptor_creation(self):
        """测试创建服务描述符"""
        factory = lambda: "test"
        descriptor = ServiceDescriptor(factory=factory, singleton=True)

        assert descriptor.factory is factory
        assert descriptor.singleton is True
        assert descriptor.instance is None

    def test_service_descriptor_default_singleton(self):
        """测试默认为单例模式"""
        descriptor = ServiceDescriptor(factory=lambda: None)

        assert descriptor.singleton is True

    def test_service_descriptor_instance_not_in_init(self):
        """测试 instance 字段不在 __init__ 中"""
        # instance 是 field(default=None, init=False)
        # 不能通过 __init__ 设置 instance，只能通过属性赋值
        import inspect

        sig = inspect.signature(ServiceDescriptor.__init__)
        params = list(sig.parameters.keys())

        # instance 不应在 __init__ 参数中
        assert "instance" not in params
        assert "factory" in params
        assert "singleton" in params

    def test_service_descriptor_can_store_instance(self):
        """测试可以存储实例"""
        descriptor = ServiceDescriptor(factory=lambda: None)

        descriptor.instance = "stored"

        assert descriptor.instance == "stored"
