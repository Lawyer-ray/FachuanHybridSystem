"""
依赖验证器

验证配置项之间的依赖关系，确保依赖的配置项存在且有效。
"""

from typing import Any, Dict, List, Set, Optional, Callable
from .base import ConfigValidator, ValidationResult, ValidationType


class DependencyValidator(ConfigValidator):
    """依赖验证器"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.DEPENDENCY
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证配置项依赖关系"""
        result = ValidationResult(is_valid=True)
        
        if field_def is None or config is None:
            return result
        
        # 验证简单依赖
        depends_on = getattr(field_def, 'depends_on', None)
        if depends_on:
            dependency_result = self._validate_simple_dependencies(key, value, depends_on, config)
            result.merge(dependency_result)
        
        # 验证条件依赖
        conditional_deps = getattr(field_def, 'conditional_dependencies', None)
        if conditional_deps:
            conditional_result = self._validate_conditional_dependencies(key, value, conditional_deps, config)
            result.merge(conditional_result)
        
        # 验证互斥依赖
        mutually_exclusive = getattr(field_def, 'mutually_exclusive', None)
        if mutually_exclusive:
            exclusive_result = self._validate_mutually_exclusive(key, value, mutually_exclusive, config)
            result.merge(exclusive_result)
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return (
            hasattr(field_def, 'depends_on') and field_def.depends_on or
            hasattr(field_def, 'conditional_dependencies') and field_def.conditional_dependencies or
            hasattr(field_def, 'mutually_exclusive') and field_def.mutually_exclusive
        )
    
    def _validate_simple_dependencies(self, key: str, value: Any, depends_on: List[str], config: Dict[str, Any]) -> ValidationResult:
        """验证简单依赖关系"""
        result = ValidationResult(is_valid=True)
        
        if not isinstance(depends_on, (list, tuple)):
            depends_on = [depends_on]
        
        for dep_key in depends_on:
            if not self._config_key_exists(dep_key, config):
                result.add_error(f"配置项 '{key}' 依赖的配置项 '{dep_key}' 不存在")
            else:
                dep_value = self._get_config_value(dep_key, config)
                if dep_value is None:
                    result.add_error(f"配置项 '{key}' 依赖的配置项 '{dep_key}' 值为空")
        
        return result
    
    def _validate_conditional_dependencies(self, key: str, value: Any, conditional_deps: Dict[str, Any], config: Dict[str, Any]) -> ValidationResult:
        """验证条件依赖关系"""
        result = ValidationResult(is_valid=True)
        
        for condition, required_keys in conditional_deps.items():
            if self._evaluate_condition(condition, value, config):
                if not isinstance(required_keys, (list, tuple)):
                    required_keys = [required_keys]
                
                for req_key in required_keys:
                    if not self._config_key_exists(req_key, config):
                        result.add_error(
                            f"配置项 '{key}' 在条件 '{condition}' 下需要配置项 '{req_key}'，但该配置项不存在"
                        )
                    else:
                        req_value = self._get_config_value(req_key, config)
                        if req_value is None:
                            result.add_error(
                                f"配置项 '{key}' 在条件 '{condition}' 下需要配置项 '{req_key}'，但该配置项值为空"
                            )
        
        return result
    
    def _validate_mutually_exclusive(self, key: str, value: Any, mutually_exclusive: List[str], config: Dict[str, Any]) -> ValidationResult:
        """验证互斥依赖关系"""
        result = ValidationResult(is_valid=True)
        
        if not isinstance(mutually_exclusive, (list, tuple)):
            mutually_exclusive = [mutually_exclusive]
        
        # 检查当前配置项是否有值
        if value is None:
            return result
        
        # 检查互斥的配置项
        existing_exclusive_keys = []
        for exclusive_key in mutually_exclusive:
            if self._config_key_exists(exclusive_key, config):
                exclusive_value = self._get_config_value(exclusive_key, config)
                if exclusive_value is not None:
                    existing_exclusive_keys.append(exclusive_key)
        
        if existing_exclusive_keys:
            exclusive_keys_str = "', '".join(existing_exclusive_keys)
            result.add_error(
                f"配置项 '{key}' 与配置项 '{exclusive_keys_str}' 互斥，不能同时设置"
            )
        
        return result
    
    def _config_key_exists(self, key: str, config: Dict[str, Any]) -> bool:
        """检查配置键是否存在"""
        keys = key.split('.')
        current = config
        
        try:
            for k in keys:
                if not isinstance(current, dict) or k not in current:
                    return False
                current = current[k]
            return True
        except (KeyError, TypeError):
            return False
    
    def _get_config_value(self, key: str, config: Dict[str, Any]) -> Any:
        """获取配置值"""
        keys = key.split('.')
        current = config
        
        try:
            for k in keys:
                if not isinstance(current, dict):
                    return None
                current = current[k]
            return current
        except (KeyError, TypeError):
            return None
    
    def _evaluate_condition(self, condition: str, value: Any, config: Dict[str, Any]) -> bool:
        """评估条件表达式"""
        try:
            # 简单的条件评估
            # 支持格式: "value == 'production'", "value != None", "config.debug == True"
            
            # 替换特殊变量
            condition = condition.replace('value', repr(value))
            
            # 处理config引用
            import re
            config_refs = re.findall(r'config\.([a-zA-Z_][a-zA-Z0-9_.]*)', condition)
            for ref in config_refs:
                config_value = self._get_config_value(ref, config)
                condition = condition.replace(f'config.{ref}', repr(config_value))
            
            # 安全的表达式评估（仅支持基本比较操作）
            allowed_names = {
                '__builtins__': {},
                'True': True,
                'False': False,
                'None': None,
            }
            
            return eval(condition, allowed_names)
        
        except Exception:
            # 条件评估失败时返回False
            return False


class CircularDependencyValidator(ConfigValidator):
    """循环依赖验证器"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.DEPENDENCY
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证循环依赖"""
        result = ValidationResult(is_valid=True)
        
        if field_def is None or config is None:
            return result
        
        # 构建依赖图
        dependency_graph = self._build_dependency_graph(config, field_def)
        
        # 检测循环依赖
        cycles = self._detect_cycles(dependency_graph)
        
        for cycle in cycles:
            if key in cycle:
                cycle_str = " -> ".join(cycle + [cycle[0]])
                result.add_error(f"检测到循环依赖: {cycle_str}")
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return hasattr(field_def, 'depends_on') and field_def.depends_on
    
    def _build_dependency_graph(self, config: Dict[str, Any], schema: Any) -> Dict[str, Set[str]]:
        """构建依赖图"""
        graph = {}
        
        # 这里需要访问完整的schema来构建依赖图
        # 简化实现，假设schema有get_all_fields方法
        if hasattr(schema, 'get_all_fields'):
            all_fields = schema.get_all_fields()
            for field_key, field_def in all_fields.items():
                depends_on = getattr(field_def, 'depends_on', None)
                if depends_on:
                    if not isinstance(depends_on, (list, tuple)):
                        depends_on = [depends_on]
                    graph[field_key] = set(depends_on)
                else:
                    graph[field_key] = set()
        
        return graph
    
    def _detect_cycles(self, graph: Dict[str, Set[str]]) -> List[List[str]]:
        """检测循环依赖"""
        cycles = []
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node: str) -> bool:
            if node in rec_stack:
                # 找到循环
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return True
            
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, set()):
                if dfs(neighbor):
                    return True
            
            rec_stack.remove(node)
            path.pop()
            return False
        
        for node in graph:
            if node not in visited:
                dfs(node)
        
        return cycles


class RequiredGroupValidator(ConfigValidator):
    """必需组验证器，验证一组配置项中至少有一个被设置"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.DEPENDENCY
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证必需组"""
        result = ValidationResult(is_valid=True)
        
        if field_def is None or config is None:
            return result
        
        required_groups = getattr(field_def, 'required_groups', None)
        if not required_groups:
            return result
        
        for group_name, group_keys in required_groups.items():
            if not isinstance(group_keys, (list, tuple)):
                group_keys = [group_keys]
            
            # 检查组中是否至少有一个配置项被设置
            has_value = False
            for group_key in group_keys:
                if self._config_key_exists(group_key, config):
                    group_value = self._get_config_value(group_key, config)
                    if group_value is not None:
                        has_value = True
                        break
            
            if not has_value:
                group_keys_str = "', '".join(group_keys)
                result.add_error(
                    f"必需组 '{group_name}' 中的配置项 ['{group_keys_str}'] 至少需要设置一个"
                )
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return hasattr(field_def, 'required_groups') and field_def.required_groups
    
    def _config_key_exists(self, key: str, config: Dict[str, Any]) -> bool:
        """检查配置键是否存在"""
        keys = key.split('.')
        current = config
        
        try:
            for k in keys:
                if not isinstance(current, dict) or k not in current:
                    return False
                current = current[k]
            return True
        except (KeyError, TypeError):
            return False
    
    def _get_config_value(self, key: str, config: Dict[str, Any]) -> Any:
        """获取配置值"""
        keys = key.split('.')
        current = config
        
        try:
            for k in keys:
                if not isinstance(current, dict):
                    return None
                current = current[k]
            return current
        except (KeyError, TypeError):
            return None