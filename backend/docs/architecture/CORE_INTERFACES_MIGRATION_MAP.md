## 目的

- 将 `apps/core/interfaces.py` 的职责拆分为 DTO/Protocol/legacy 基础设施的单一来源，降低重复定义与漂移风险
- 保持向后兼容：短期仍允许 `from apps.core.interfaces import ...`，但其内容逐步退化为 re-export

## 现状分类（interfaces.py）

### DTO（dataclass）

- LoginAttemptResult → `apps/core/dto/auth.py`
- TokenAcquisitionResult → `apps/core/dto/auth.py`
- AccountCredentialDTO → `apps/core/dto/organization.py`
- LawyerDTO → `apps/core/dto/organization.py`
- LawFirmDTO → `apps/core/dto/organization.py`
- ClientDTO → `apps/core/dto/client.py`
- ContractDTO → `apps/core/dto/contracts.py`
- CaseDTO → `apps/core/dto/cases.py`

### Protocol（跨模块能力契约）

- `interfaces.py` 内的 `Protocol` 定义 → `apps/core/protocols/*.py`（按业务域拆分），由 `apps/core/protocols/__init__.py` 统一导出

### ServiceLocator / EventBus（基础设施）

- ServiceLocator → `apps/core/service_locator.py`（mixin 版，唯一实现）
- EventBus → `apps/core/event_bus.py`
- ~~LegacyServiceLocator~~ → 已删除（`legacy_service_locator.py` 已移除）
- ~~service_locator_proxy.py~~ → 已删除

### 兼容入口

- `apps/core/interfaces/` 包作为兼容性 re-export 层：
  - `from apps.core.interfaces import ServiceLocator` → 重导出自 `apps.core.service_locator`
  - `from apps.core.interfaces import EventBus, Events` → 重导出自 `apps.core.event_bus`
  - `from apps.core.interfaces import CaseDTO, ...` → 重导出自 `apps.core.dtos`
  - `from apps.core.interfaces import ICaseService, ...` → 重导出自 `apps.core.protocols`

## 影响面（依赖方）

- 当前后端存在大量模块直接 import `apps.core.interfaces`（数量级为数百）。因此迁移采取“先新增单一来源 + interfaces re-export 兼容”方式，避免一次性改动全仓调用点。

## 护栏（结构测试）

- 禁止在 `apps/core/interfaces/` 包中新增 `@dataclass` 定义（DTO 必须在 `apps/core/dto/**`）
- 禁止在 `apps/core/interfaces/` 包中新增 `class X(Protocol)` 定义（Protocol 必须在 `apps/core/protocols/**`）
- 禁止引用已删除的 `LegacyServiceLocator`（统一使用 `apps.core.service_locator.ServiceLocator`）
