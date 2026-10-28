"""一张网诉讼材料（ajsscl）手动拉取的单元测试。

全部 mock 掉 HTTP 与登录，不依赖真实一张网接口。

覆盖：
1. 列表解析（只取有 url 的项、去掉路径成分防穿越）
2. 空数组是正常结果（不是错误）
3. 拉到本地 → CaseLog + CaseLogAttachment
4. 按文件名幂等（重复拉取不重复建）
5. 单个文件失败不影响其它文件
6. 全部失败 / 全部已存在时不产生空日志
7. 类型白名单与大小上限沿用系统 CASE_LOG_* 常量
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from plugins.court_automation.case_sync.materials import (
    MaterialPullResult,
    YizhangwangMaterial,
    YizhangwangMaterialError,
    _allowed_extensions,
    _max_file_bytes,
    fetch_materials,
    pull_materials,
)

pytestmark = pytest.mark.django_db

#: 测试用 PDF 字节（真实 PDF 头，便于被下游识别）
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def lawyer(db: Any) -> Any:
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create(username="yz_mat_lawyer", real_name="测试律师")


@pytest.fixture
def case(db: Any) -> Any:
    from apps.cases.models import Case

    return Case.objects.create(yz_wid="aj-mat-1", name="材料拉取测试案件")


def _material(name: str, ext: str = "pdf", url: str = "https://oss.example.com/a.pdf?sig=1") -> YizhangwangMaterial:
    return YizhangwangMaterial(name=name, extname=ext, url=url)


# ---------------------------------------------------------------------------
# 列表解析
# ---------------------------------------------------------------------------


def _fake_response(payload: dict[str, Any], status: int = 200) -> Any:
    class _Resp:
        status_code = status

        def json(self) -> dict[str, Any]:
            return payload

    return _Resp()


def test_fetch_materials_parses_list() -> None:
    payload = {
        "code": 200,
        "data": [
            {"name": "6-证据清单.pdf", "extname": "pdf", "url": "https://oss/a.pdf"},
            {"name": "7-证据明细.PDF", "extname": "PDF", "url": "https://oss/b.pdf"},
            {"name": "无url项.pdf", "extname": "pdf"},  # 无 url → 丢弃
            "not-a-dict",  # 非 dict → 丢弃
        ],
    }
    with patch("plugins.court_automation.case_sync.materials.httpx.get", return_value=_fake_response(payload)):
        materials = fetch_materials("aj-1", "token")

    assert len(materials) == 2
    assert materials[0].name == "6-证据清单.pdf"
    assert materials[1].extname == "pdf"  # 统一小写


def test_fetch_materials_empty_is_normal() -> None:
    """空数组是正常结果（该案件没有材料），不是错误。"""
    with patch(
        "plugins.court_automation.case_sync.materials.httpx.get",
        return_value=_fake_response({"code": 200, "data": []}),
    ):
        assert fetch_materials("aj-1", "token") == []

    # data 为 null 同样按空处理
    with patch(
        "plugins.court_automation.case_sync.materials.httpx.get",
        return_value=_fake_response({"code": 200, "data": None}),
    ):
        assert fetch_materials("aj-1", "token") == []


def test_fetch_materials_rejects_bad_code() -> None:
    """业务失败时 HTTP 仍可能是 200，必须看 code。"""
    with patch(
        "plugins.court_automation.case_sync.materials.httpx.get",
        return_value=_fake_response({"code": 500, "message": "系统异常"}),
    ):
        with pytest.raises(YizhangwangMaterialError, match="系统异常"):
            fetch_materials("aj-1", "token")


def test_fetch_materials_rejects_401() -> None:
    with patch(
        "plugins.court_automation.case_sync.materials.httpx.get",
        return_value=_fake_response({}, status=401),
    ):
        with pytest.raises(YizhangwangMaterialError, match="登录态失效"):
            fetch_materials("aj-1", "token")


def test_safe_name_strips_path_components() -> None:
    """文件名去掉任何路径成分，防目录穿越。"""
    assert _material("../../etc/passwd.pdf").safe_name == "passwd.pdf"
    assert _material("a/b/c.pdf").safe_name == "c.pdf"
    assert _material("").safe_name.endswith(".pdf")


# ---------------------------------------------------------------------------
# 拉取落库
# ---------------------------------------------------------------------------


def _run_pull(case: Any, lawyer: Any, materials: list[YizhangwangMaterial], downloads: dict[str, bytes]) -> Any:
    """mock 登录 + 列表 + 下载，跑一次拉取。

    downloads: {文件名: 字节}；缺省视为下载失败。
    """

    def fake_download(material: YizhangwangMaterial) -> tuple[bytes, str]:
        if material.safe_name in downloads:
            return downloads[material.safe_name], material.safe_name
        raise YizhangwangMaterialError("HTTP 403")

    credential = {"id": "1", "account": "test", "password": "test"}  # pragma: allowlist secret
    with (
        patch(
            "plugins.court_automation.case_sync.client.resolve_lawyer_credential",
            return_value=credential,
        ),
        patch(
            "plugins.court_automation.case_sync.client.acquire_zxfw_token",
            return_value="token",
        ),
        patch(
            "plugins.court_automation.case_sync.materials.fetch_materials",
            return_value=materials,
        ),
        patch(
            "plugins.court_automation.case_sync.materials._download",
            side_effect=fake_download,
        ),
    ):
        return pull_materials(case=case, lawyer=lawyer)


def test_pull_materials_creates_log_and_attachments(case: Any, lawyer: Any) -> None:
    from apps.cases.models import CaseLog, CaseLogAttachment

    materials = [_material("证据清单.pdf"), _material("证据明细.pdf")]
    result = _run_pull(
        case,
        lawyer,
        materials,
        {"证据清单.pdf": PDF_BYTES, "证据明细.pdf": PDF_BYTES},
    )

    assert isinstance(result, MaterialPullResult)
    assert result.remote_count == 2
    assert set(result.downloaded) == {"证据清单.pdf", "证据明细.pdf"}
    assert result.log_id is not None

    log = CaseLog.objects.get(pk=result.log_id)
    assert log.case_id == case.pk
    assert log.actor_id == lawyer.pk
    assert "一张网材料拉取" in log.content

    names = set(CaseLogAttachment.objects.filter(log=log).values_list("original_filename", flat=True))
    assert names == {"证据清单.pdf", "证据明细.pdf"}


def test_pull_materials_is_idempotent(case: Any, lawyer: Any) -> None:
    """重复拉取：已存在的文件名跳过，不重复建日志。"""
    from apps.cases.models import CaseLog

    materials = [_material("证据清单.pdf")]
    downloads = {"证据清单.pdf": PDF_BYTES}

    first = _run_pull(case, lawyer, materials, downloads)
    assert first.has_new is True

    second = _run_pull(case, lawyer, materials, downloads)
    assert second.has_new is False
    assert second.skipped == ["证据清单.pdf"]
    assert second.log_id is None
    assert CaseLog.objects.filter(case=case).count() == 1


def test_pull_materials_partial_failure_keeps_successes(case: Any, lawyer: Any) -> None:
    """单个文件下载失败不影响其它文件（预签名过期是现场常态）。"""
    materials = [_material("ok.pdf"), _material("expired.pdf")]
    result = _run_pull(case, lawyer, materials, {"ok.pdf": PDF_BYTES})

    assert result.downloaded == ["ok.pdf"]
    assert len(result.failed) == 1
    assert result.failed[0][0] == "expired.pdf"


def test_pull_materials_all_failed_creates_no_log(case: Any, lawyer: Any) -> None:
    """全部失败时不沉淀空日志。"""
    from apps.cases.models import CaseLog

    result = _run_pull(case, lawyer, [_material("a.pdf")], {})

    assert result.downloaded == []
    assert len(result.failed) == 1
    assert result.log_id is None
    assert CaseLog.objects.filter(case=case).count() == 0


def test_pull_materials_empty_list_creates_no_log(case: Any, lawyer: Any) -> None:
    from apps.cases.models import CaseLog

    result = _run_pull(case, lawyer, [], {})

    assert result.remote_count == 0
    assert result.log_id is None
    assert CaseLog.objects.filter(case=case).count() == 0


def test_pull_materials_rejects_when_no_yzw_id(db: Any, lawyer: Any) -> None:
    from apps.cases.models import Case

    case = Case.objects.create(yz_wid="", name="无一张网ID")
    with pytest.raises(YizhangwangMaterialError, match="请先填写"):
        pull_materials(case=case, lawyer=lawyer)


def test_pull_materials_skips_disallowed_extension(case: Any, lawyer: Any) -> None:
    """白名单外的扩展名不下载，记为失败。"""
    result = _run_pull(case, lawyer, [_material("evil.exe", ext="exe")], {"evil.exe": b"MZ"})

    assert result.downloaded == []
    assert len(result.failed) == 1
    assert "不支持的类型" in result.failed[0][1]


# ---------------------------------------------------------------------------
# 常量与系统一致
# ---------------------------------------------------------------------------


def test_limits_follow_system_constants() -> None:
    """扩展名白名单与大小上限必须沿用 CASE_LOG_*，避免两套规则漂移。"""
    from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS

    assert _allowed_extensions() == {str(e).lower().lstrip(".") for e in CASE_LOG_ALLOWED_EXTENSIONS}
    assert _max_file_bytes() > 0
