"""
依赖注入容器 - 统一管理依赖关系，减少硬编码依赖

设计目标：
1. 消除硬编码的模块依赖
2. 提供单例管理和生命周期控制
3. 支持依赖注入和测试替换
4. 简化模块间的通信
"""

from typing import Dict, Any, Callable, Optional, Type, TypeVar
from functools import lru_cache
import inspect


T = TypeVar('T')


class ServiceDescriptor:
    """服务描述符 - 描述服务的创建方式和生命周期"""
    
    def __init__(self, factory: Callable, 
                 lifetime: str = 'singleton',
                 dependencies: Optional[list] = None):
        """
        初始化服务描述符
        
        Args:
            factory: 服务工厂函数
            lifetime: 生命周期 (singleton, transient, scoped)
            dependencies: 依赖项列表
        """
        self.factory = factory
        self.lifetime = lifetime
        self.dependencies = dependencies or []
        self.instance = None  # 单例实例
        self.initialized = False


class DIContainer:
    """
    依赖注入容器 - 管理所有服务的生命周期和依赖关系
    """
    
    def __init__(self):
        """初始化依赖注入容器"""
        self._services: Dict[str, ServiceDescriptor] = {}
        self._singleton_cache: Dict[str, Any] = {}
        self._scoped_cache: Dict[str, Any] = {}
        
        # 注册核心服务
        self._register_core_services()
    
    def _register_core_services(self):
        """注册核心服务"""
        # 配置管理器
        self.register_singleton('config_manager', lambda: self._create_config_manager())
        
        # 缓存管理器
        self.register_singleton('cache', lambda: self._create_cache())
        
        # 日志管理器
        self.register_singleton('logger', lambda: self._create_logger())
    
    # ==================== 服务注册方法 ====================
    
    def register_singleton(self, name: str, factory: Callable, dependencies: Optional[list] = None):
        """
        注册单例服务
        
        Args:
            name: 服务名称
            factory: 工厂函数
            dependencies: 依赖项列表
        """
        descriptor = ServiceDescriptor(factory, 'singleton', dependencies)
        self._services[name] = descriptor
    
    def register_transient(self, name: str, factory: Callable, dependencies: Optional[list] = None):
        """
        注册瞬时服务（每次请求创建新实例）
        
        Args:
            name: 服务名称
            factory: 工厂函数
            dependencies: 依赖项列表
        """
        descriptor = ServiceDescriptor(factory, 'transient', dependencies)
        self._services[name] = descriptor
    
    def register_scoped(self, name: str, factory: Callable, dependencies: Optional[list] = None):
        """
        注册作用域服务（每个作用域内单例）
        
        Args:
            name: 服务名称
            factory: 工厂函数
            dependencies: 依赖项列表
        """
        descriptor = ServiceDescriptor(factory, 'scoped', dependencies)
        self._services[name] = descriptor
    
    def register_instance(self, name: str, instance: Any):
        """
        注册已存在的实例
        
        Args:
            name: 服务名称
            instance: 实例对象
        """
        descriptor = ServiceDescriptor(lambda: instance, 'singleton')
        descriptor.instance = instance
        descriptor.initialized = True
        self._services[name] = descriptor
    
    # ==================== 服务解析方法 ====================
    
    def resolve(self, name: str) -> Any:
        """
        解析服务
        
        Args:
            name: 服务名称
        
        Returns:
            服务实例
        """
        if name not in self._services:
            raise KeyError(f"服务未注册: {name}")
        
        descriptor = self._services[name]
        
        # 根据生命周期返回实例
        if descriptor.lifetime == 'singleton':
            return self._resolve_singleton(name, descriptor)
        elif descriptor.lifetime == 'transient':
            return self._resolve_transient(descriptor)
        elif descriptor.lifetime == 'scoped':
            return self._resolve_scoped(name, descriptor)
        else:
            raise ValueError(f"未知的生命周期: {descriptor.lifetime}")
    
    def resolve_by_type(self, service_type: Type[T]) -> T:
        """
        按类型解析服务
        
        Args:
            service_type: 服务类型
        
        Returns:
            服务实例
        """
        # 首先按类型名称查找
        type_name = service_type.__name__
        for name, descriptor in self._services.items():
            instance = self.resolve(name)
            if isinstance(instance, service_type):
                return instance
        
        # 如果找不到，尝试创建新实例
        try:
            # 检查构造函数参数
            signature = inspect.signature(service_type.__init__)
            params = list(signature.parameters.keys())[1:]  # 跳过self
            
            # 解析依赖
            dependencies = {}
            for param in params:
                # 尝试按名称解析
                try:
                    dependencies[param] = self.resolve(param)
                except KeyError:
                    # 尝试按类型解析
                    for name, descriptor in self._services.items():
                        instance = self.resolve(name)
                        if hasattr(instance, '__class__'):
                            if param == instance.__class__.__name__.lower():
                                dependencies[param] = instance
                                break
            
            # 创建实例
            instance = service_type(**dependencies)
            return instance
            
        except Exception as e:
            raise ValueError(f"无法解析类型 {service_type}: {e}")
    
    def _resolve_singleton(self, name: str, descriptor: ServiceDescriptor) -> Any:
        """解析单例服务"""
        if name in self._singleton_cache:
            return self._singleton_cache[name]
        
        # 创建实例
        instance = self._create_instance(descriptor)
        self._singleton_cache[name] = instance
        
        return instance
    
    def _resolve_transient(self, descriptor: ServiceDescriptor) -> Any:
        """解析瞬时服务"""
        return self._create_instance(descriptor)
    
    def _resolve_scoped(self, name: str, descriptor: ServiceDescriptor) -> Any:
        """解析作用域服务"""
        if name in self._scoped_cache:
            return self._scoped_cache[name]
        
        # 创建实例
        instance = self._create_instance(descriptor)
        self._scoped_cache[name] = instance
        
        return instance
    
    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """创建服务实例"""
        # 如果已有实例，直接返回
        if descriptor.initialized and descriptor.instance is not None:
            return descriptor.instance
        
        # 解析依赖
        dependencies = {}
        for dep_name in descriptor.dependencies:
            dependencies[dep_name] = self.resolve(dep_name)
        
        # 创建实例
        if dependencies:
            instance = descriptor.factory(**dependencies)
        else:
            instance = descriptor.factory()
        
        # 更新描述符
        descriptor.instance = instance
        descriptor.initialized = True
        
        return instance
    
    # ==================== 核心服务工厂方法 ====================
    
    def _create_config_manager(self):
        """创建配置管理器"""
        from .config_manager import ConfigManager
        return ConfigManager()
    
    def _create_cache(self):
        """创建缓存管理器"""
        from .cache import get_cache
        return get_cache()
    
    def _create_logger(self):
        """创建日志管理器"""
        from .logger import get_logger
        return get_logger("di_container")
    
    # ==================== 作用域管理 ====================
    
    def create_scope(self) -> 'DIContainer':
        """
        创建新的作用域
        
        Returns:
            新的作用域容器
        """
        scope_container = DIContainer()
        
        # 复制服务注册（共享父容器的服务定义）
        scope_container._services = self._services.copy()
        
        # 新的作用域缓存
        scope_container._singleton_cache = self._singleton_cache.copy()
        scope_container._scoped_cache = {}  # 每个作用域有自己的scoped缓存
        
        return scope_container
    
    def clear_scope(self):
        """清除当前作用域缓存"""
        self._scoped_cache.clear()
    
    def clear_cache(self):
        """清除所有缓存"""
        self._singleton_cache.clear()
        self._scoped_cache.clear()
    
    # ==================== 实用方法 ====================
    
    def has_service(self, name: str) -> bool:
        """检查是否注册了指定服务"""
        return name in self._services
    
    def get_registered_services(self) -> list:
        """获取所有已注册的服务名称"""
        return list(self._services.keys())
    
    def auto_register(self, module_path: str):
        """
        自动注册模块中的所有服务
        
        Args:
            module_path: 模块路径
        """
        import importlib
        module = importlib.import_module(module_path)
        
        # 遍历模块中的类
        for name in dir(module):
            obj = getattr(module, name)
            
            # 检查是否是类
            if isinstance(obj, type) and hasattr(obj, '__module__'):
                if obj.__module__ == module_path:
                    # 注册为单例
                    service_name = name.lower()
                    self.register_singleton(service_name, lambda c=obj: self.resolve_by_type(c))
    
    # ==================== 装饰器 ====================
    
    def inject(self, *dependencies):
        """
        依赖注入装饰器
        
        Args:
            *dependencies: 依赖项名称列表
        
        Returns:
            装饰器函数
        """
        def decorator(func):
            def wrapper(*args, **kwargs):
                # 解析依赖
                resolved_deps = {}
                for dep in dependencies:
                    resolved_deps[dep] = self.resolve(dep)
                
                # 合并参数
                kwargs.update(resolved_deps)
                
                # 调用函数
                return func(*args, **kwargs)
            
            return wrapper
        
        return decorator
    
    def singleton(self, name: Optional[str] = None):
        """
        单例装饰器
        
        Args:
            name: 服务名称，如果为None则使用类名小写
        
        Returns:
            装饰器函数
        """
        def decorator(cls):
            nonlocal name
            if name is None:
                name = cls.__name__.lower()
            
            self.register_singleton(name, lambda: cls())
            
            # 添加静态方法到类
            @classmethod
            def get_instance(cls_ref):
                return self.resolve(name)
            
            cls.get_instance = get_instance
            
            return cls
        
        return decorator


# 全局容器实例
_global_container: Optional[DIContainer] = None


def get_container() -> DIContainer:
    """获取全局依赖注入容器实例"""
    global _global_container
    if _global_container is None:
        _global_container = DIContainer()
    return _global_container


def set_container(container: DIContainer):
    """设置全局依赖注入容器实例（用于测试）"""
    global _global_container
    _global_container = container


# 便捷函数
def resolve(service_name: str) -> Any:
    """解析服务"""
    return get_container().resolve(service_name)


def resolve_by_type(service_type: Type[T]) -> T:
    """按类型解析服务"""
    return get_container().resolve_by_type(service_type)


def inject(*dependencies):
    """依赖注入装饰器"""
    return get_container().inject(*dependencies)


def singleton(name: Optional[str] = None):
    """单例装饰器"""
    return get_container().singleton(name)