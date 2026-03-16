from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.apps import apps as django_apps

logger = logging.getLogger("apps.oa_filing")

_executor = ThreadPoolExecutor(max_workers=2)

# 系统支持的 OA 站点（site_name 需与账号密码管理中的「网站名称」一致）
SUPPORTED_SITES: list[str] = ["金诚同达OA"]


class ScriptExecutorService:
    """OA 立案执行服务。按 site_name 分发到对应律所脚本。"""

    def execute(
        self,
        site_name: str,
        contract_id: int,
        case_id: int | None,
        user: Any,
    ) -> Any:
        from apps.oa_filing.models import FilingSession, SessionStatus
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        credential_model = django_apps.get_model("organization", "AccountCredential")
        credential = credential_model.objects.filter(
            lawyer=user,
            site_name=site_name,
        ).first()
        if credential is None:
            raise ScriptExecutionError(f"未找到匹配凭证: 站点名称={site_name}")

        session: FilingSession = FilingSession.objects.create(
            contract_id=contract_id,
            case_id=case_id,
            oa_config=None,
            credential=credential,
            user=user,
            status=SessionStatus.IN_PROGRESS,
        )
        logger.info("开始立案: session=%d, site=%s", session.id, site_name)

        _executor.submit(
            self._run_in_thread,
            session.id,
            site_name,
            credential,
            contract_id,
            case_id,
        )

        return FilingSession.objects.get(pk=session.id)

    def _run_in_thread(
        self,
        session_id: int,
        site_name: str,
        credential: Any,
        contract_id: int,
        case_id: int | None,
    ) -> None:
        """后台线程：执行脚本并更新会话状态。"""
        from apps.oa_filing.models import FilingSession, SessionStatus

        try:
            self._dispatch(site_name, credential, contract_id, case_id)
            FilingSession.objects.filter(pk=session_id).update(status=SessionStatus.COMPLETED)
            logger.info("立案完成: session=%d", session_id)
        except Exception as exc:
            FilingSession.objects.filter(pk=session_id).update(
                status=SessionStatus.FAILED,
                error_message=str(exc),
            )
            logger.error("立案失败: session=%d, error=%s", session_id, exc)

    def _dispatch(
        self,
        site_name: str,
        credential: Any,
        contract_id: int,
        case_id: int | None,
    ) -> None:
        """按 site_name 分发到对应脚本。"""
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        if site_name == "金诚同达OA":
            self._run_jtn(credential, contract_id, case_id)
        else:
            raise ScriptExecutionError(f"不支持的OA系统: {site_name}")

    def _run_jtn(self, credential: Any, contract_id: int, case_id: int | None) -> None:
        """执行金诚同达 OA 立案。"""
        from apps.oa_filing.services.exceptions import ScriptExecutionError
        from apps.oa_filing.services.oa_scripts.jtn_filing import (
            CaseInfo,
            ClientInfo,
            ConflictPartyInfo,
            ContractInfo,
            JtnFilingScript,
        )
        case_model = django_apps.get_model("cases", "Case")
        contract_model = django_apps.get_model("contracts", "Contract")
        contract_assignment_model = django_apps.get_model("contracts", "ContractAssignment")
        contract_party_model = django_apps.get_model("contracts", "ContractParty")

        # ── 委托方（PRINCIPAL） ──
        principal_parties: list[Any] = list(
            contract_party_model.objects.filter(
                contract_id=contract_id,
                role="PRINCIPAL",
            ).select_related("client")
        )
        clients: list[ClientInfo] = []
        for party in principal_parties:
            c = party.client
            clients.append(
                ClientInfo(
                    name=c.name,
                    client_type=c.client_type,
                    id_number=c.id_number,
                    address=c.address,
                    phone=c.phone,
                    legal_representative=c.legal_representative,
                )
            )
        if not clients:
            raise ScriptExecutionError("合同没有委托方当事人")

        # ── 案件负责人（主办律师 real_name） ──
        primary_assignment = (
            contract_assignment_model.objects.filter(
                contract_id=contract_id,
                is_primary=True,
            )
            .select_related("lawyer")
            .first()
        )
        manager_name: str = ""
        if primary_assignment is not None:
            manager_name = primary_assignment.lawyer.real_name or ""

        # ── 案件信息 ──
        contract = contract_model.objects.get(pk=contract_id)

        if case_id is not None:
            case = case_model.objects.get(pk=case_id)
            category = self._map_case_category(case)
            stage = self._map_case_stage(case)
            which_side = self._map_which_side(case, contract_id)
            start_date = str(case.start_date) if case.start_date else ""
        else:
            case = None
            # 常法/专项合同无案件，按合同类型推断
            contract_type_map: dict[str, str] = {
                "advisor": "01",
                "special": "02",
            }
            category = contract_type_map.get(contract.case_type or "", "01")
            stage = ""
            which_side = "01"
            start_date = str(contract.start_date) if contract.start_date else ""

        kindtype, kindtype_sed = self._map_kindtype(category, principal_parties)

        case_info = CaseInfo(
            manager_id="",
            manager_name=manager_name,
            category=category,
            stage=stage,
            which_side=which_side,
            kindtype=kindtype,
            kindtype_sed=kindtype_sed,
            kindtype_thr="",
            case_name=contract.name,
            case_desc=contract.name,
            start_date=start_date,
            contact_name="/",
            contact_phone="/",
        )

        # ── 对方当事人（OPPOSING → 利冲） ──
        opposing_parties: list[Any] = list(
            contract_party_model.objects.filter(
                contract_id=contract_id,
                role="OPPOSING",
            ).select_related("client")
        )
        conflict_parties: list[ConflictPartyInfo] = []
        for party in opposing_parties:
            c = party.client
            conflict_parties.append(
                ConflictPartyInfo(
                    name=c.name,
                    legal_position=self._map_legal_position(party),
                    customer_type="11" if c.client_type == "natural" else "01",
                    id_number=c.id_number,
                )
            )

        # ── 合同信息（预盖章份数 = 我方当事人数 + 2） ──
        stamp_count: int = len(principal_parties) + 2
        contract_info = ContractInfo(
            rec_type=self._map_fee_mode(contract),
            currency="RMB",
            contract_type="30",
            is_free="N",
            start_date=str(contract.start_date) if contract.start_date else "",
            end_date=str(contract.end_date) if contract.end_date else "",
            amount=str(int(contract.fixed_amount)) if contract.fixed_amount else "",
            stamp_count=stamp_count,
        )

        script = JtnFilingScript(
            account=str(credential.account),
            password=str(credential.password),
        )
        script.run(
            clients,
            case_info=case_info,
            conflict_parties=conflict_parties,
            contract_info=contract_info,
        )

    def _map_case_category(self, case: Any) -> str:
        """将系统案件类型映射到 OA category_id。

        OA 值: 01=常年法律顾问, 02=专项法律服务, 03=民商事,
               04=行政（复议）, 05=刑事, 06=仲裁
        """
        mapping: dict[str | None, str] = {
            "civil": "03",  # 民商事
            "criminal": "05",  # 刑事
            "administrative": "04",  # 行政（复议）
            "labor": "03",  # 劳动仲裁 → 民商事
            "intl": "06",  # 商事仲裁
            "execution": "03",  # 申请执行 → 民商事
            "bankruptcy": "03",  # 破产 → 民商事
            "special": "02",  # 专项服务
            "advisor": "01",  # 常法顾问
        }
        return mapping.get(case.case_type, "03")

    def _map_case_stage(self, case: Any) -> str:
        """将系统案件阶段映射到 OA stage_id。

        OA 民商事(03): 0301=一审, 0305=二审, 0310=申请再审, 0313=再审,
                        0308=申诉, 0309=申诉抗诉, 0314=执行
        OA 行政(04):   0401=行政复议, 0402=一审, 0403=二审, 0404=重审一审,
                        0405=重审二审, 0406=申诉, 0408=申请再审, 0409=提审,
                        0410=再审一审, 0411=再审二审
        OA 刑事(05):   0500=自诉, 0501=侦查, 0502=审查起诉, 0503=一审,
                        0504=二审, 0507=重审一审, 0508=重审二审, 0509=申诉,
                        0510=提审, 0511=死刑复核, 0512=再审一审, 0513=再审二审
        非诉(01/02):   无阶段
        """
        category: str = self._map_case_category(case)

        # 非诉类型没有阶段
        if category in ("01", "02"):
            return ""

        stage: str | None = case.current_stage

        # 民商事(03)
        civil_mapping: dict[str | None, str] = {
            "first_trial": "0301",
            "second_trial": "0305",
            "enforcement": "0314",
            "apply_retrial": "0310",
            "retrial_first": "0313",
            "retrial_second": "0313",
            "rehearing_first": "0313",
            "rehearing_second": "0313",
            "petition": "0308",
            "apply_protest": "0309",
            "petition_protest": "0309",
            "review": "0310",
        }

        # 行政(04)
        admin_mapping: dict[str | None, str] = {
            "administrative_review": "0401",
            "first_trial": "0402",
            "second_trial": "0403",
            "retrial_first": "0404",
            "retrial_second": "0405",
            "petition": "0406",
            "apply_retrial": "0408",
            "review": "0409",
            "rehearing_first": "0410",
            "rehearing_second": "0411",
        }

        # 刑事(05) / 仲裁(06) — OA 共用同一套阶段
        criminal_mapping: dict[str | None, str] = {
            "private_prosecution": "0500",
            "investigation": "0501",
            "prosecution_review": "0502",
            "first_trial": "0503",
            "second_trial": "0504",
            "retrial_first": "0507",
            "retrial_second": "0508",
            "petition": "0509",
            "review": "0510",
            "death_penalty_review": "0511",
            "rehearing_first": "0512",
            "rehearing_second": "0513",
            "apply_retrial": "0509",
            "apply_protest": "0509",
            "petition_protest": "0509",
        }

        if category == "03":
            return civil_mapping.get(stage, "0301")
        if category == "04":
            return admin_mapping.get(stage, "0402")
        # 05 刑事 / 06 仲裁
        return criminal_mapping.get(stage, "0503")

    def _map_which_side(self, case: Any, contract_id: int) -> str:
        """从案件我方当事人诉讼地位推断代理何方。取第一个我方当事人的诉讼地位。"""
        case_party_model = django_apps.get_model("cases", "CaseParty")
        contract_party_model = django_apps.get_model("contracts", "ContractParty")
        our_client_ids = set(
            contract_party_model.objects.filter(
                contract_id=contract_id, role="PRINCIPAL"
            ).values_list("client_id", flat=True)
        )
        party = case_party_model.objects.filter(case=case, client_id__in=our_client_ids).first()
        mapping = {"plaintiff": "01", "defendant": "02", "third": "09"}
        return mapping.get(getattr(party, "legal_status", None) or "", "01")

    def _map_legal_position(self, contract_party: Any) -> str:
        """从 CaseParty 取对方当事人诉讼地位，映射到 OA 法律地位值。"""
        case_party_model = django_apps.get_model("cases", "CaseParty")
        case_party = case_party_model.objects.filter(
            client_id=contract_party.client_id
        ).first()
        mapping = {"plaintiff": "01", "defendant": "02", "third": "09"}
        return mapping.get(getattr(case_party, "legal_status", None) or "", "02")

    def _map_fee_mode(self, contract: Any) -> str:
        """将系统收费模式映射到 OA rec_type。

        OA 只有: 01=定额收费, 02=按标的比例收费, 03=按小时收费
        """
        mapping: dict[str | None, str] = {
            "FIXED": "01",  # 定额收费
            "SEMI_RISK": "02",  # 半风险 → 按标的比例
            "FULL_RISK": "02",  # 全风险 → 按标的比例
            "CUSTOM": "01",  # 自定义 → 定额
        }
        return mapping.get(contract.fee_mode, "01")

    def _map_kindtype(self, category: str, principal_parties: list[Any]) -> tuple[str, str]:
        """根据案件类型和委托方推断业务种类一级/二级。

        category 01（常年法律顾问）：
          一级 KindType01_01=企业 / KindType01_05=个人
          二级 KindType01_0103=民营企业（默认）
        category 02（专项法律服务）：
          一级 KindType02_01=企业专项 / KindType02_05=个人专项
        诉讼类（03/04/05/06）：无业务种类，返回空。
        """
        if category not in ("01", "02"):
            return "", ""

        # 判断委托方是否为自然人
        has_natural = any(
            getattr(p, "client", None) and getattr(p.client, "client_type", "") == "natural"
            for p in principal_parties
        )

        if category == "01":
            if has_natural:
                return "KindType01_05", ""
            # 企业：默认民营企业
            return "KindType01_01", "KindType01_0103"

        # category == "02"
        if has_natural:
            return "KindType02_05", ""
        return "KindType02_01", ""
