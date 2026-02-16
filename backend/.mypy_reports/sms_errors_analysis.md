# SMS Module Mypy Errors Analysis

SMS module errors: 301
Errors from other modules: 1488
Total errors: 1789

## Errors from Other Modules (Dependencies)

- apps/automation: 619 errors
- apps/core: 251 errors
- apps/documents: 187 errors
- apps/cases: 167 errors
- apps/contracts: 121 errors
- apps/organization: 104 errors
- apps/client: 39 errors

## SMS Module Error Breakdown

### [attr-defined] - 191 errors

**attachment_query_service.py** (3 errors)
- Line 38: no attribute "result"
- Line 56: no attribute "result"
- Line 129: has no attribute "name"

**attachment_upload_service.py** (3 errors)
- Line 73: has no attribute "name"
- Line 227: has no attribute "name"
- Line 259: has no attribute "name"

**court_sms_helpers.py** (7 errors)
- Line 114: "_SMSHelperHost" has no attribute "_refresh_scraper_task_status"
- Line 185: "_SMSHelperHost" has no attribute "_add_case_numbers_to_case"
- Line 187: attribute "pk"
- Line 217: attribute "pk"
- Line 246: "_SMSHelperHost" has no attribute "_extract_from_single_doc"
- ... and 2 more

**court_sms_service.py** (84 errors)
- Line 156: no attribute "id"
- Line 161: no attribute "id"
- Line 162: no attribute "id"
- Line 165: no attribute "id"
- Line 207: no attribute "case_id"
- ... and 79 more

**sms_notification_service.py** (14 errors)
- Line 100: "CourtSMS" has no attribute "id"
- Line 100: has no attribute "id"
- Line 104: "ICaseChatService" has no attribute "get_or_create_chat"
- Line 105: has no attribute "id"
- Line 108: "CourtSMS" has no attribute "id"
- ... and 9 more

**base.py** (3 errors)
- Line 73: attribute "id"
- Line 77: attribute "id"
- Line 81: attribute "id"

**sms_downloading_stage.py** (11 errors)
- Line 85: "CourtSMS" has no attribute "id"
- Line 93: "CourtSMS" has no attribute "id"
- Line 94: "ScraperTask" has no attribute "id"
- Line 99: "CourtSMS" has no attribute "id"
- Line 105: "CourtSMS" has no attribute "id"
- ... and 6 more

**sms_matching_stage.py** (14 errors)
- Line 136: "CourtSMS" has no attribute "id"
- Line 136: has no attribute "id"
- Line 156: has no attribute "id"
- Line 168: "ScraperTask" has no attribute "documents"
- Line 182: "CourtSMS" has no attribute "id"
- ... and 9 more

**sms_notifying_stage.py** (4 errors)
- Line 112: "CourtSMS" has no attribute "id"
- Line 168: "CourtSMS" has no attribute "id"
- Line 174: "CourtSMS" has no attribute "id"
- Line 189: "CourtSMS" has no attribute "id"

**sms_parsing_stage.py** (1 errors)
- Line 112: "CourtSMS" has no attribute "id"

**sms_renaming_stage.py** (12 errors)
- Line 91: "CourtSMS" has no attribute "id"
- Line 97: "CourtSMS" has no attribute "id"
- Line 117: "CourtSMS" has no attribute "id"
- Line 135: has no attribute "result"
- Line 139: has no attribute "result"
- ... and 7 more

**sms_submission_service.py** (18 errors)
- Line 105: "CourtSMS" has no attribute "id"
- Line 110: "CourtSMS" has no attribute "id"
- Line 111: "CourtSMS" has no attribute "id"
- Line 114: "CourtSMS" has no attribute "id"
- Line 156: "CourtSMS" has no attribute "case_id"
- ... and 13 more

**task_recovery_service.py** (17 errors)
- Line 63: has no attribute "extend"
- Line 177: has no attribute "id"
- Line 195: has no attribute "id"
- Line 202: has no attribute "id"
- Line 203: has no attribute "id"
- ... and 12 more

### [valid-type] - 37 errors

**case_number_extractor_service.py** (6 errors)
- Line 60: Invalid type comment or annotation
- Line 118: Invalid type comment or annotation
- Line 212: Invalid type comment or annotation
- Line 301: Invalid type comment or annotation
- Line 386: Invalid type comment or annotation
- ... and 1 more

**document_attachment_service.py** (5 errors)
- Line 53: Invalid type comment or annotation
- Line 100: Invalid type comment or annotation
- Line 170: Invalid type comment or annotation
- Line 171: Invalid type comment or annotation
- Line 223: Invalid type comment or annotation

**document_parser_service.py** (4 errors)
- Line 50: Invalid type comment or annotation
- Line 95: Invalid type comment or annotation
- Line 147: Invalid type comment or annotation
- Line 190: Invalid type comment or annotation

**party_matching_service.py** (4 errors)
- Line 49: Invalid type comment or annotation
- Line 119: Invalid type comment or annotation
- Line 178: Invalid type comment or annotation
- Line 197: Invalid type comment or annotation

**sms_notification_service.py** (1 errors)
- Line 70: type comment or annotation

**sms_parser_service.py** (9 errors)
- Line 27: comment or annotation
- Line 28: comment or annotation
- Line 29: comment or annotation
- Line 141: comment or annotation
- Line 200: comment or annotation
- ... and 4 more

**sms_matching_stage.py** (1 errors)
- Line 222: Invalid type comment or annotation

**sms_notifying_stage.py** (1 errors)
- Line 132: Invalid type comment or annotation

**sms_renaming_stage.py** (4 errors)
- Line 130: Invalid type comment or annotation
- Line 144: Invalid type comment or annotation
- Line 178: Invalid type comment or annotation
- Line 206: Invalid type comment or annotation

**task_recovery_service.py** (2 errors)
- Line 137: type comment or annotation
- Line 156: type comment or annotation

### [name-defined] - 28 errors

**court_sms_service.py** (14 errors)
- Line 33: "CaseNumberExtractorService" is not defined
- Line 34: "DocumentAttachmentService" is not defined
- Line 35: "SMSNotificationService" is not defined
- Line 36: "ICaseService" is not defined
- Line 37: "IClientService" is not defined
- ... and 9 more

**document_attachment_service.py** (11 errors)
- Line 25: "ICaseService" is not defined
- Line 26: "DocumentRenamer" is not defined
- Line 39: "ICaseService" is not defined
- Line 46: "DocumentRenamer" is not defined
- Line 53: "CourtSMS" is not defined
- ... and 6 more

**sms_notification_service.py** (1 errors)
- Line 147: "CaseChat" is not defined

**task_recovery_service.py** (2 errors)
- Line 25: is not defined
- Line 104: "Dict" is not defined

### [unknown] - 16 errors

**case_number_extractor_service.py** (1 errors)
- Line 77: "IDocumentProcessingService" has no attribute

**court_sms_helpers.py** (2 errors)
- Line 182: "ILawyerService" has no attribute "get_lawyer_internal"; maybe
- Line 237: "_SMSHelperHost" has no attribute "_get_document_paths_for_extraction"

**court_sms_service.py** (1 errors)
- Line 124: default for argument "received_at" (default has type "None", argument has type

**document_attachment_service.py** (2 errors)
- Line 65: type annotation for "document_paths" (hint:
- Line 112: type annotation for "document_paths" (hint:

**feishu_bot_service.py** (4 errors)
- Line 208: types in assignment (expression has type "str", target has type "bool | None")
- Line 218: types in assignment (expression has type "str", target has type "bool | None")
- Line 259: types in assignment (expression has type "str", target has type "bool | None")
- Line 265: types in assignment (expression has type "str", target has type "bool | None")

**document_parser_service.py** (2 errors)
- Line 72: "IDocumentProcessingService" has no attribute
- Line 147: Function is missing a type annotation for one or more arguments

**sms_matching_stage.py** (1 errors)
- Line 253: "ILawyerService" has no attribute "get_lawyer_internal"; maybe

**sms_renaming_stage.py** (1 errors)
- Line 164: "ILawyerService" has no attribute "get_lawyer_internal"; maybe

**sms_submission_service.py** (2 errors)
- Line 73: Incompatible default for argument "received_at" (default has type "None",
- Line 278: "ILawyerService" has no attribute "get_lawyer_internal"; maybe

### [no-any-return] - 13 errors

**document_renamer.py** (1 errors)
- Line 119: from function declared to return "str | None"

**feishu_bot_service.py** (7 errors)
- Line 44: from function declared to return "str"
- Line 61: from function declared to return "str"
- Line 71: from function declared to return "int"
- Line 77: from function declared to return "int"
- Line 288: from function declared to return "bool"
- ... and 2 more

**sms_downloading_stage.py** (1 errors)
- Line 64: Returning Any from function declared to return "bool"

**sms_matching_stage.py** (1 errors)
- Line 83: Returning Any from function declared to return "bool"

**sms_notifying_stage.py** (1 errors)
- Line 90: Returning Any from function declared to return "bool"

**sms_parsing_stage.py** (1 errors)
- Line 76: Any from function declared to return "bool"

**sms_renaming_stage.py** (1 errors)
- Line 70: Returning Any from function declared to return "bool"

### [operator] - 5 errors

**task_recovery_service.py** (5 errors)
- Line 79: operand types for + ("object" and "int")
- Line 82: operand types for + ("object" and "int")
- Line 88: operand types for + ("object" and "int")
- Line 90: operand types for + ("object" and "int")
- Line 93: operand types for + ("object" and "int")

### [str, Any] - 5 errors

**court_sms_service.py** (4 errors)
- Line 1121: return value type (got "CourtSMS", expected "dict[str, Any]")
- Line 1132: return value type (got "CourtSMS", expected "dict[str, Any]")
- Line 1143: return value type (got "CourtSMS", expected "dict[str, Any]")
- Line 1160: return value type (got "CourtSMS", expected "dict[str, Any]")

**task_recovery_service.py** (1 errors)
- Line 314: Any from function declared to return "dict[str, Any]"

### [str] - 3 errors

**case_matcher.py** (3 errors)
- Line 210: function declared to return "list[str]"
- Line 223: function declared to return "list[str]"
- Line 231: function declared to return "list[str]"

### [call-arg] - 1 errors

**sms_notification_service.py** (1 errors)
- Line 26: arguments for "getLogger"

### [Any] - 1 errors

**case_matcher.py** (1 errors)
- Line 74: function declared to return "list[Any]"

### [union-attr] - 1 errors

**case_matcher.py** (1 errors)
- Line 126: "Any | None" has no attribute "name"

