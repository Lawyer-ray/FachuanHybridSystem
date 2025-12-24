"""
Steering 依赖管理模块

本模块实现了 Steering 规范系统的依赖管理功能，包括：
- 依赖关系解析和验证
- 循环依赖检测
- 加载顺序优化
- 依赖冲突解决
- 依赖图可视化

Requirements: 8.4
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, NamedTuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging
import threading
import json

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """依赖类型"""
    INHERITS = "inherits"  # 继承依赖
    REQUIRES = "requires"  # 必需依赖
    OPTIONAL = "optional"  # 可选依赖
    CONFLICTS = "conflicts"  # 冲突依赖


class LoadOrderStrategy(Enum):
    """加载顺序策略"""
    PRIORITY = "priority"  # 按优先级排序
    DEPENDENCY = "dependency"  # 按依赖关系排序
    ALPHABETICAL = "alphabetical"  # 按字母顺序排序
    TOPOLOGICAL = "topological"  # 拓扑排序
    CUSTOM = "custom"  # 自定义排序


@dataclass
class DependencyInfo:
    """依赖信息"""
    source_spec: str
    target_spec: str
    dependency_type: DependencyType
    version_constraint: Optional[str] = None
    condition: Optional[str] = None  # 条件依赖
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpecificationMetadata:
    """规范元数据"""
    path: str
    name: str
    version: str = "1.0.0"
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    description: str = ""
    author: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    # 依赖信息
    inherits: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    optional_deps: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    
    # 加载配置
    inclusion: str = "manual"  # always, fileMatch, manual
    file_match_pattern: Optional[str] = None
    load_condition: Optional[str] = None


@dataclass
class DependencyConflict:
    """依赖冲突"""
    conflict_type: str  # circular, missing, version, conflict
    description: str
    affected_specs: List[str]
    suggested_resolution: Optional[str] = None


@dataclass
class LoadOrderResult:
    """加载顺序结果"""
    ordered_specs: List[str]
    dependency_levels: Dict[str, int]  # 规范 -> 依赖层级
    conflicts: List[DependencyConflict]
    warnings: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class DependencyGraph:
    """依赖图"""
    
    def __init__(self):
        self.nodes: Dict[str, SpecificationMetadata] = {}
        self.edges: Dict[str, List[DependencyInfo]] = defaultdict(list)
        self.reverse_edges: Dict[str, List[DependencyInfo]] = defaultdict(list)
        self._lock = threading.RLock()
    
    def add_specification(self, metadata: SpecificationMetadata):
        """添加规范"""
        with self._lock:
            self.nodes[metadata.path] = metadata
            
            # 添加依赖边
            self._add_dependencies(metadata)
    
    def _add_dependencies(self, metadata: SpecificationMetadata):
        """添加依赖关系"""
        spec_path = metadata.path
        
        # 继承依赖
        for inherit_path in metadata.inherits:
            dep_info = DependencyInfo(
                source_spec=spec_path,
                target_spec=inherit_path,
                dependency_type=DependencyType.INHERITS
            )
            self.edges[spec_path].append(dep_info)
            self.reverse_edges[inherit_path].append(dep_info)
        
        # 必需依赖
        for require_path in metadata.requires:
            dep_info = DependencyInfo(
                source_spec=spec_path,
                target_spec=require_path,
                dependency_type=DependencyType.REQUIRES
            )
            self.edges[spec_path].append(dep_info)
            self.reverse_edges[require_path].append(dep_info)
        
        # 可选依赖
        for optional_path in metadata.optional_deps:
            dep_info = DependencyInfo(
                source_spec=spec_path,
                target_spec=optional_path,
                dependency_type=DependencyType.OPTIONAL
            )
            self.edges[spec_path].append(dep_info)
            self.reverse_edges[optional_path].append(dep_info)
        
        # 冲突依赖
        for conflict_path in metadata.conflicts:
            dep_info = DependencyInfo(
                source_spec=spec_path,
                target_spec=conflict_path,
                dependency_type=DependencyType.CONFLICTS
            )
            self.edges[spec_path].append(dep_info)
    
    def get_dependencies(self, spec_path: str, 
                        dependency_types: Optional[List[DependencyType]] = None) -> List[DependencyInfo]:
        """获取规范的依赖"""
        with self._lock:
            if spec_path not in self.edges:
                return []
            
            dependencies = self.edges[spec_path]
            
            if dependency_types:
                dependencies = [dep for dep in dependencies 
                              if dep.dependency_type in dependency_types]
            
            return dependencies
    
    def get_dependents(self, spec_path: str,
                      dependency_types: Optional[List[DependencyType]] = None) -> List[DependencyInfo]:
        """获取依赖于指定规范的其他规范"""
        with self._lock:
            if spec_path not in self.reverse_edges:
                return []
            
            dependents = self.reverse_edges[spec_path]
            
            if dependency_types:
                dependents = [dep for dep in dependents 
                            if dep.dependency_type in dependency_types]
            
            return dependents
    
    def detect_circular_dependencies(self) -> List[List[str]]:
        """检测循环依赖"""
        with self._lock:
            cycles = []
            visited = set()
            rec_stack = set()
            
            def dfs(node: str, path: List[str]) -> bool:
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
                
                # 只考虑强依赖（继承和必需）
                dependencies = self.get_dependencies(
                    node, [DependencyType.INHERITS, DependencyType.REQUIRES]
                )
                
                for dep in dependencies:
                    if dep.target_spec in self.nodes:
                        if dfs(dep.target_spec, path + [node]):
                            return True
                
                rec_stack.remove(node)
                return False
            
            for node in self.nodes:
                if node not in visited:
                    dfs(node, [])
            
            return cycles
    
    def topological_sort(self, specs: List[str]) -> Tuple[List[str], List[DependencyConflict]]:
        """拓扑排序"""
        with self._lock:
            # 只考虑指定的规范
            subgraph_nodes = set(specs)
            conflicts = []
            
            # 计算入度
            in_degree = {spec: 0 for spec in subgraph_nodes}
            
            for spec in subgraph_nodes:
                dependencies = self.get_dependencies(
                    spec, [DependencyType.INHERITS, DependencyType.REQUIRES]
                )
                
                for dep in dependencies:
                    if dep.target_spec in subgraph_nodes:
                        in_degree[spec] += 1
            
            # 拓扑排序
            queue = deque([spec for spec in subgraph_nodes if in_degree[spec] == 0])
            result = []
            
            while queue:
                current = queue.popleft()
                result.append(current)
                
                # 更新依赖于当前节点的节点
                dependents = self.get_dependents(
                    current, [DependencyType.INHERITS, DependencyType.REQUIRES]
                )
                
                for dep in dependents:
                    if dep.source_spec in subgraph_nodes:
                        in_degree[dep.source_spec] -= 1
                        if in_degree[dep.source_spec] == 0:
                            queue.append(dep.source_spec)
            
            # 检查是否有循环依赖
            if len(result) != len(subgraph_nodes):
                remaining_specs = subgraph_nodes - set(result)
                conflicts.append(DependencyConflict(
                    conflict_type="circular",
                    description=f"检测到循环依赖，涉及规范: {', '.join(remaining_specs)}",
                    affected_specs=list(remaining_specs),
                    suggested_resolution="请检查并移除循环依赖关系"
                ))
                
                # 将剩余的规范添加到结果中（按字母顺序）
                result.extend(sorted(remaining_specs))
            
            return result, conflicts
    
    def validate_dependencies(self, specs: List[str]) -> List[DependencyConflict]:
        """验证依赖关系"""
        with self._lock:
            conflicts = []
            
            for spec in specs:
                if spec not in self.nodes:
                    continue
                
                # 检查必需依赖是否存在
                required_deps = self.get_dependencies(
                    spec, [DependencyType.INHERITS, DependencyType.REQUIRES]
                )
                
                for dep in required_deps:
                    if dep.target_spec not in self.nodes:
                        conflicts.append(DependencyConflict(
                            conflict_type="missing",
                            description=f"规范 {spec} 依赖的 {dep.target_spec} 不存在",
                            affected_specs=[spec, dep.target_spec],
                            suggested_resolution=f"请确保 {dep.target_spec} 文件存在"
                        ))
                    elif dep.target_spec not in specs:
                        conflicts.append(DependencyConflict(
                            conflict_type="missing",
                            description=f"规范 {spec} 依赖的 {dep.target_spec} 未包含在加载列表中",
                            affected_specs=[spec, dep.target_spec],
                            suggested_resolution=f"请将 {dep.target_spec} 添加到加载列表"
                        ))
                
                # 检查冲突依赖
                conflict_deps = self.get_dependencies(spec, [DependencyType.CONFLICTS])
                
                for dep in conflict_deps:
                    if dep.target_spec in specs:
                        conflicts.append(DependencyConflict(
                            conflict_type="conflict",
                            description=f"规范 {spec} 与 {dep.target_spec} 存在冲突",
                            affected_specs=[spec, dep.target_spec],
                            suggested_resolution=f"请移除 {dep.target_spec} 或解决冲突"
                        ))
            
            return conflicts
    
    def get_dependency_levels(self, specs: List[str]) -> Dict[str, int]:
        """计算依赖层级"""
        with self._lock:
            levels = {}
            
            def calculate_level(spec: str, visited: Set[str]) -> int:
                if spec in levels:
                    return levels[spec]
                
                if spec in visited:
                    # 循环依赖，返回默认层级
                    return 0
                
                visited.add(spec)
                
                # 计算依赖的最大层级
                max_dep_level = -1
                dependencies = self.get_dependencies(
                    spec, [DependencyType.INHERITS, DependencyType.REQUIRES]
                )
                
                for dep in dependencies:
                    if dep.target_spec in specs:
                        dep_level = calculate_level(dep.target_spec, visited.copy())
                        max_dep_level = max(max_dep_level, dep_level)
                
                level = max_dep_level + 1
                levels[spec] = level
                return level
            
            for spec in specs:
                if spec not in levels:
                    calculate_level(spec, set())
            
            return levels


class SteeringDependencyManager:
    """Steering 依赖管理器"""
    
    def __init__(self, config: Dict[str, Any], steering_root: str = ".kiro/steering"):
        self.config = config
        self.steering_root = Path(steering_root)
        self.dependency_graph = DependencyGraph()
        self._metadata_cache: Dict[str, SpecificationMetadata] = {}
        self._lock = threading.RLock()
        
        # 配置参数
        self.auto_resolve = config.get("auto_resolve", True)
        self.max_depth = config.get("max_depth", 10)
        self.circular_detection = config.get("circular_detection", True)
        self.load_order_strategy = LoadOrderStrategy(
            config.get("load_order_strategy", "dependency")
        )
        
        # 加载所有规范元数据
        self._load_all_metadata()
    
    def _load_all_metadata(self):
        """加载所有规范元数据"""
        if not self.steering_root.exists():
            logger.warning(f"Steering 根目录不存在: {self.steering_root}")
            return
        
        for spec_file in self.steering_root.rglob("*.md"):
            try:
                rel_path = spec_file.relative_to(self.steering_root)
                spec_path = str(rel_path)
                
                metadata = self._load_specification_metadata(spec_path)
                if metadata:
                    self._metadata_cache[spec_path] = metadata
                    self.dependency_graph.add_specification(metadata)
                    
            except Exception as e:
                logger.warning(f"加载规范元数据失败 {spec_file}: {e}")
    
    def _load_specification_metadata(self, spec_path: str) -> Optional[SpecificationMetadata]:
        """加载单个规范的元数据"""
        full_path = self.steering_root / spec_path
        
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 front-matter
            metadata_dict = {}
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    try:
                        metadata_dict = yaml.safe_load(parts[1]) or {}
                    except yaml.YAMLError as e:
                        logger.warning(f"解析 front-matter 失败 {spec_path}: {e}")
            
            # 创建元数据对象
            metadata = SpecificationMetadata(
                path=spec_path,
                name=metadata_dict.get("name", spec_path),
                version=metadata_dict.get("version", "1.0.0"),
                priority=metadata_dict.get("priority", 0),
                tags=metadata_dict.get("tags", []),
                description=metadata_dict.get("description", ""),
                author=metadata_dict.get("author", ""),
                created_at=metadata_dict.get("created_at"),
                updated_at=metadata_dict.get("updated_at"),
                
                # 依赖信息
                inherits=self._normalize_dependency_list(metadata_dict.get("inherits", [])),
                requires=self._normalize_dependency_list(metadata_dict.get("requires", [])),
                optional_deps=self._normalize_dependency_list(metadata_dict.get("optional", [])),
                conflicts=self._normalize_dependency_list(metadata_dict.get("conflicts", [])),
                
                # 加载配置
                inclusion=metadata_dict.get("inclusion", "manual"),
                file_match_pattern=metadata_dict.get("fileMatchPattern"),
                load_condition=metadata_dict.get("loadCondition")
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"加载规范元数据失败 {spec_path}: {e}")
            return None
    
    def _normalize_dependency_list(self, deps: Any) -> List[str]:
        """标准化依赖列表"""
        if isinstance(deps, str):
            return [deps]
        elif isinstance(deps, list):
            return [str(dep) for dep in deps]
        else:
            return []
    
    def resolve_load_order(self, spec_paths: List[str]) -> LoadOrderResult:
        """解析加载顺序"""
        with self._lock:
            conflicts = []
            warnings = []
            
            # 验证依赖关系
            validation_conflicts = self.dependency_graph.validate_dependencies(spec_paths)
            conflicts.extend(validation_conflicts)
            
            # 检测循环依赖
            if self.circular_detection:
                cycles = self.dependency_graph.detect_circular_dependencies()
                for cycle in cycles:
                    conflicts.append(DependencyConflict(
                        conflict_type="circular",
                        description=f"检测到循环依赖: {' -> '.join(cycle)}",
                        affected_specs=cycle,
                        suggested_resolution="请移除循环依赖关系"
                    ))
            
            # 根据策略排序
            if self.load_order_strategy == LoadOrderStrategy.DEPENDENCY:
                ordered_specs, topo_conflicts = self.dependency_graph.topological_sort(spec_paths)
                conflicts.extend(topo_conflicts)
            elif self.load_order_strategy == LoadOrderStrategy.PRIORITY:
                ordered_specs = self._sort_by_priority(spec_paths)
            elif self.load_order_strategy == LoadOrderStrategy.ALPHABETICAL:
                ordered_specs = sorted(spec_paths)
            elif self.load_order_strategy == LoadOrderStrategy.TOPOLOGICAL:
                ordered_specs, topo_conflicts = self.dependency_graph.topological_sort(spec_paths)
                conflicts.extend(topo_conflicts)
            else:
                # 默认使用依赖排序
                ordered_specs, topo_conflicts = self.dependency_graph.topological_sort(spec_paths)
                conflicts.extend(topo_conflicts)
            
            # 计算依赖层级
            dependency_levels = self.dependency_graph.get_dependency_levels(ordered_specs)
            
            # 添加缺失的规范（如果启用自动解析）
            if self.auto_resolve:
                resolved_specs = self._resolve_missing_dependencies(ordered_specs)
                if len(resolved_specs) > len(ordered_specs):
                    warnings.append(f"自动添加了 {len(resolved_specs) - len(ordered_specs)} 个依赖规范")
                    ordered_specs = resolved_specs
            
            return LoadOrderResult(
                ordered_specs=ordered_specs,
                dependency_levels=dependency_levels,
                conflicts=conflicts,
                warnings=warnings,
                metadata={
                    "strategy": self.load_order_strategy.value,
                    "auto_resolve": self.auto_resolve,
                    "total_specs": len(ordered_specs)
                }
            )
    
    def _sort_by_priority(self, spec_paths: List[str]) -> List[str]:
        """按优先级排序"""
        def get_priority(spec_path: str) -> int:
            metadata = self._metadata_cache.get(spec_path)
            return metadata.priority if metadata else 0
        
        return sorted(spec_paths, key=get_priority, reverse=True)
    
    def _resolve_missing_dependencies(self, spec_paths: List[str]) -> List[str]:
        """解析缺失的依赖"""
        resolved_specs = set(spec_paths)
        to_process = deque(spec_paths)
        depth = 0
        
        while to_process and depth < self.max_depth:
            current_spec = to_process.popleft()
            
            if current_spec not in self._metadata_cache:
                continue
            
            # 获取强依赖
            dependencies = self.dependency_graph.get_dependencies(
                current_spec, [DependencyType.INHERITS, DependencyType.REQUIRES]
            )
            
            for dep in dependencies:
                if dep.target_spec not in resolved_specs and dep.target_spec in self._metadata_cache:
                    resolved_specs.add(dep.target_spec)
                    to_process.append(dep.target_spec)
            
            depth += 1
        
        # 重新排序
        if self.load_order_strategy == LoadOrderStrategy.DEPENDENCY:
            ordered_specs, _ = self.dependency_graph.topological_sort(list(resolved_specs))
        else:
            ordered_specs = self._sort_by_priority(list(resolved_specs))
        
        return ordered_specs
    
    def get_dependency_info(self, spec_path: str) -> Dict[str, Any]:
        """获取规范的依赖信息"""
        with self._lock:
            if spec_path not in self._metadata_cache:
                return {"error": f"规范不存在: {spec_path}"}
            
            metadata = self._metadata_cache[spec_path]
            
            # 获取直接依赖
            direct_deps = self.dependency_graph.get_dependencies(spec_path)
            
            # 获取被依赖信息
            dependents = self.dependency_graph.get_dependents(spec_path)
            
            return {
                "metadata": {
                    "name": metadata.name,
                    "version": metadata.version,
                    "priority": metadata.priority,
                    "tags": metadata.tags,
                    "description": metadata.description
                },
                "dependencies": {
                    "inherits": metadata.inherits,
                    "requires": metadata.requires,
                    "optional": metadata.optional_deps,
                    "conflicts": metadata.conflicts
                },
                "direct_dependencies": [
                    {
                        "target": dep.target_spec,
                        "type": dep.dependency_type.value,
                        "condition": dep.condition
                    }
                    for dep in direct_deps
                ],
                "dependents": [
                    {
                        "source": dep.source_spec,
                        "type": dep.dependency_type.value
                    }
                    for dep in dependents
                ]
            }
    
    def export_dependency_graph(self, output_path: str, format: str = "json"):
        """导出依赖图"""
        with self._lock:
            graph_data = {
                "nodes": {},
                "edges": []
            }
            
            # 导出节点
            for spec_path, metadata in self._metadata_cache.items():
                graph_data["nodes"][spec_path] = {
                    "name": metadata.name,
                    "version": metadata.version,
                    "priority": metadata.priority,
                    "tags": metadata.tags,
                    "description": metadata.description
                }
            
            # 导出边
            for spec_path in self._metadata_cache:
                dependencies = self.dependency_graph.get_dependencies(spec_path)
                for dep in dependencies:
                    graph_data["edges"].append({
                        "source": dep.source_spec,
                        "target": dep.target_spec,
                        "type": dep.dependency_type.value,
                        "condition": dep.condition
                    })
            
            # 保存文件
            try:
                if format.lower() == "json":
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(graph_data, f, indent=2, ensure_ascii=False)
                else:
                    raise ValueError(f"不支持的格式: {format}")
                
                logger.info(f"依赖图已导出到: {output_path}")
                
            except Exception as e:
                logger.error(f"导出依赖图失败: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取依赖管理统计信息"""
        with self._lock:
            total_specs = len(self._metadata_cache)
            
            # 统计依赖类型
            dep_type_counts = defaultdict(int)
            total_deps = 0
            
            for spec_path in self._metadata_cache:
                dependencies = self.dependency_graph.get_dependencies(spec_path)
                total_deps += len(dependencies)
                
                for dep in dependencies:
                    dep_type_counts[dep.dependency_type.value] += 1
            
            # 检测问题
            cycles = self.dependency_graph.detect_circular_dependencies()
            all_specs = list(self._metadata_cache.keys())
            validation_conflicts = self.dependency_graph.validate_dependencies(all_specs)
            
            return {
                "total_specifications": total_specs,
                "total_dependencies": total_deps,
                "dependency_types": dict(dep_type_counts),
                "circular_dependencies": len(cycles),
                "validation_conflicts": len(validation_conflicts),
                "average_dependencies_per_spec": total_deps / total_specs if total_specs > 0 else 0,
                "config": {
                    "auto_resolve": self.auto_resolve,
                    "max_depth": self.max_depth,
                    "circular_detection": self.circular_detection,
                    "load_order_strategy": self.load_order_strategy.value
                }
            }
    
    def refresh_metadata(self):
        """刷新元数据"""
        with self._lock:
            self._metadata_cache.clear()
            self.dependency_graph = DependencyGraph()
            self._load_all_metadata()
            logger.info("依赖管理器元数据已刷新")


def create_dependency_manager_from_config(config: Dict[str, Any], 
                                        steering_root: str = ".kiro/steering") -> SteeringDependencyManager:
    """根据配置创建依赖管理器"""
    return SteeringDependencyManager(config, steering_root)