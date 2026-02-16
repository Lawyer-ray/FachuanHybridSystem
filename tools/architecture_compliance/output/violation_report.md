# 架构违规报告

扫描时间: 2026-02-11 11:59:38

## 总览

违规总数: **35**

### 按类型统计

| 类型 | 数量 |
| --- | --- |
| api_direct_orm_access | 8 |
| service_cross_module_import | 15 |
| service_static_method_abuse | 12 |

### 按严重程度统计

| 严重程度 | 数量 |
| --- | --- |
| high | 23 |
| medium | 12 |

## 详细违规列表

### api_direct_orm_access (8个)

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 175)
  - 严重程度: high
  - 描述: API层直接使用ORM: DocumentRecognitionTask.objects.create()
  - 代码片段:
    ```python
    task = DocumentRecognitionTask.objects.create(
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 449)
  - 严重程度: high
  - 描述: API层直接使用ORM: DocumentRecognitionTask.objects.get()
  - 代码片段:
    ```python
    task = DocumentRecognitionTask.objects.get(id=task_id)
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 299)
  - 严重程度: high
  - 描述: API层直接使用ORM: CaseNumber.objects.filter()
  - 代码片段:
    ```python
    case_ids_by_number = CaseNumber.objects.filter(
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 304)
  - 严重程度: high
  - 描述: API层直接使用ORM: CaseParty.objects.filter()
  - 代码片段:
    ```python
    case_ids_by_party = CaseParty.objects.filter(
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 309)
  - 严重程度: high
  - 描述: API层直接使用ORM: Case.objects.filter()
  - 代码片段:
    ```python
    cases = Case.objects.filter(
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 205)
  - 严重程度: high
  - 描述: API层直接访问ORM manager: DocumentRecognitionTask.objects
  - 代码片段:
    ```python
    task = DocumentRecognitionTask.objects.select_related('case').get(id=task_id)
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 363)
  - 严重程度: high
  - 描述: API层直接访问ORM manager: DocumentRecognitionTask.objects
  - 代码片段:
    ```python
    task = DocumentRecognitionTask.objects.select_related('case').get(id=task_id)
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/court_document_recognition_api.py** (行 288)
  - 严重程度: high
  - 描述: API层直接访问ORM manager: Case.objects
  - 代码片段:
    ```python
    cases = Case.objects.select_related().prefetch_related(
    ```

### service_cross_module_import (15个)

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/chat/feishu_provider.py** (行 103)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.core.models import SystemConfig
  - 代码片段:
    ```python
    from apps.core.models import SystemConfig
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/chat/owner_config_manager.py** (行 89)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.core.models import SystemConfig
  - 代码片段:
    ```python
    from apps.core.models import SystemConfig
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/court_document_recognition/case_binding_service.py** (行 459)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.cases.models import Case, CaseLog
  - 代码片段:
    ```python
    from apps.cases.models import Case, CaseLog
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/court_document_recognition/case_binding_service.py** (行 235)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.cases.models import CaseLog
  - 代码片段:
    ```python
    from apps.cases.models import CaseLog
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/court_document_recognition/task_service.py** (行 141)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.cases.models import Case, CaseNumber, CaseParty
  - 代码片段:
    ```python
    from apps.cases.models import Case, CaseNumber, CaseParty
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/cases/services/case_service.py** (行 1204)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.organization.models import Lawyer
  - 代码片段:
    ```python
    from apps.organization.models import Lawyer
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/cases/services/chat_name_config_service.py** (行 24)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.core.models import SystemConfig
  - 代码片段:
    ```python
    from apps.core.models import SystemConfig
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/cases/services/data/cause_court_data_service.py** (行 429)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.core.models import CauseOfAction
  - 代码片段:
    ```python
    from apps.core.models import CauseOfAction
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/contracts/services/contract_admin_service.py** (行 113)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.cases.models import Case, CaseParty, CaseAssignment, SimpleCaseType
  - 代码片段:
    ```python
    from apps.cases.models import Case, CaseParty, CaseAssignment, SimpleCaseType
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/documents/services/generation/context_builder.py** (行 19)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.contracts.models import PartyRole
  - 代码片段:
    ```python
    from apps.contracts.models import PartyRole
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/documents/services/generation/supplementary_agreement_generation_service.py** (行 12)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.contracts.models import PartyRole
  - 代码片段:
    ```python
    from apps.contracts.models import PartyRole
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/documents/services/placeholders/supplementary/opposing_service.py** (行 10)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.contracts.models import PartyRole
  - 代码片段:
    ```python
    from apps.contracts.models import PartyRole
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/documents/services/placeholders/supplementary/opposing_service.py** (行 11)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.client.models import Client
  - 代码片段:
    ```python
    from apps.client.models import Client
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/documents/services/placeholders/supplementary/principal_service.py** (行 73)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.contracts.models import PartyRole
  - 代码片段:
    ```python
    from apps.contracts.models import PartyRole
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/documents/services/placeholders/supplementary/principal_service.py** (行 98)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.contracts.models import PartyRole
  - 代码片段:
    ```python
    from apps.contracts.models import PartyRole
    ```

### service_static_method_abuse (12个)

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/court_document_recognition/text_extraction_service.py** (行 326)
  - 严重程度: medium
  - 描述: Service类 TextExtractionService 中使用@staticmethod: is_supported_format()
  - 代码片段:
    ```python
    def is_supported_format(file_path: str) -> bool:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/court_document_recognition/text_extraction_service.py** (行 344)
  - 严重程度: medium
  - 描述: Service类 TextExtractionService 中使用@staticmethod: get_supported_extensions()
  - 代码片段:
    ```python
    def get_supported_extensions() -> Tuple[str, ...]:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/browser_manager.py** (行 38)
  - 严重程度: medium
  - 描述: Service类 BrowserManager 中使用@staticmethod: create_browser()
  - 代码片段:
    ```python
    def create_browser(
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/browser_manager.py** (行 147)
  - 严重程度: medium
  - 描述: Service类 BrowserManager 中使用@staticmethod: _apply_anti_detection()
  - 代码片段:
    ```python
    def _apply_anti_detection(context_args: dict) -> dict:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/browser_manager.py** (行 169)
  - 严重程度: medium
  - 描述: Service类 BrowserManager 中使用@staticmethod: _inject_stealth_script()
  - 代码片段:
    ```python
    def _inject_stealth_script(page: Page) -> None:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/browser_manager.py** (行 181)
  - 严重程度: medium
  - 描述: Service类 BrowserManager 中使用@staticmethod: _cleanup()
  - 代码片段:
    ```python
    def _cleanup(
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/security_service.py** (行 78)
  - 严重程度: medium
  - 描述: Service类 SecurityService 中使用@staticmethod: mask_sensitive_data()
  - 代码片段:
    ```python
    def mask_sensitive_data(data: dict, keys: list = None) -> dict:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/security_service.py** (行 105)
  - 严重程度: medium
  - 描述: Service类 SecurityService 中使用@staticmethod: encrypt_config()
  - 代码片段:
    ```python
    def encrypt_config(config: dict) -> dict:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/scraper/core/security_service.py** (行 128)
  - 严重程度: medium
  - 描述: Service类 SecurityService 中使用@staticmethod: decrypt_config()
  - 代码片段:
    ```python
    def decrypt_config(config: dict) -> dict:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/cases/services/case_number_service.py** (行 340)
  - 严重程度: medium
  - 描述: Service类 CaseNumberService 中使用@staticmethod: normalize_case_number()
  - 代码片段:
    ```python
    def normalize_case_number(number: str) -> str:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/cases/services/case_service.py** (行 124)
  - 严重程度: medium
  - 描述: Service类 CaseService 中使用@staticmethod: get_case_queryset()
  - 代码片段:
    ```python
    def get_case_queryset() -> QuerySet:
    ```

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/client/services/property_clue_service.py** (行 362)
  - 严重程度: medium
  - 描述: Service类 PropertyClueService 中使用@staticmethod: get_content_template()
  - 代码片段:
    ```python
    def get_content_template(clue_type: str) -> str:
    ```
