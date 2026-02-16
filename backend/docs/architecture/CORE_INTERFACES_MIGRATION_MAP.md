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

### LegacyServiceLocator / EventBus（遗留基础设施）

- LegacyServiceLocator → `apps/core/legacy_service_locator.py`
- EventBus → `apps/core/event_bus.py`

### 兼容入口

- `apps/core/interfaces.py` 逐步收敛为兼容性 re-export：\n  - `from apps.core.dto.* import ...`\n  - `from apps.core.protocols import ...`\n  - `from apps.core.legacy_service_locator import LegacyServiceLocator`\n  - `from apps.core.event_bus import EventBus`

## 影响面（依赖方）

- 当前后端存在大量模块直接 import `apps.core.interfaces`（数量级为数百）。因此迁移采取“先新增单一来源 + interfaces re-export 兼容”方式，避免一次性改动全仓调用点。

## 护栏（结构测试）

- 禁止在 `apps/core/interfaces.py` 新增 `@dataclass` 定义（DTO 必须在 `apps/core/dto/**`）
- 禁止在 `apps/core/interfaces.py` 新增 `class X(Protocol)` 定义（Protocol 必须在 `apps/core/protocols/**`）
- 禁止新增对 `LegacyServiceLocator/EventBus` 的直接引用扩散（允许 wiring/基础设施层白名单）
