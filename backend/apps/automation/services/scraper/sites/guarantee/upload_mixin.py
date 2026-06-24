"""gThree 材料上传：起诉状、身份证、证据。"""

from __future__ import annotations

import asyncio
import mimetypes
import re
from pathlib import Path
from typing import Any


class GuaranteeUploadMixin:  # pragma: no cover
    """gThree 材料上传：起诉状、身份证、证据。"""

    page: Any
    _material_items: list[dict[str, str]]

    def _build_file_payload(self, file_path: str) -> str | dict[str, Any]:
        """构造 Playwright set_input_files 载荷，使用原始文件名而非 UUID 存储名。"""
        for entry in self._material_items:
            if entry["path"] == file_path:
                original_name = entry.get("original_name", "")
                if original_name:
                    try:
                        mime, _ = mimetypes.guess_type(original_name)
                        return {
                            "name": original_name,
                            "mimeType": mime or "application/octet-stream",
                            "buffer": Path(file_path).read_bytes(),
                        }
                    except OSError:
                        pass
                break
        return file_path

    def _build_file_payloads(self, file_paths: list[str]) -> str | list[str] | dict[str, Any] | list[dict[str, Any]]:
        """为多个文件构造带原始文件名的 Playwright 载荷。"""
        payloads: list[str | dict[str, Any]] = []
        for fp in file_paths:
            payloads.append(self._build_file_payload(fp))
        if len(payloads) == 1:
            return payloads[0]
        return payloads  # type: ignore[return-value]

    def _complete_g_three(self, case_data: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        result: dict[str, Any] = {"uploaded": 0, "next_clicked": None, "uploads": []}
        raw_paths = case_data.get("material_paths") or []
        items: list[dict[str, str]] = []
        for item in raw_paths:
            if isinstance(item, dict):
                p = str(item.get("path") or "")
                if p:
                    items.append(
                        {
                            "path": p,
                            "type_name": str(item.get("type_name") or ""),
                            "original_name": str(item.get("original_name") or ""),
                        }
                    )
            else:
                p = str(item)
                if p:
                    items.append({"path": p, "type_name": "", "original_name": ""})
        if not items:
            return result

        used: set[str] = set()

        def _pick_path(  # pragma: no cover
            keyword_groups: list[list[str]],
            *,
            type_name_groups: list[list[str]] | None = None,
            exclude_type_names: list[str] | None = None,
        ) -> str | None:
            if type_name_groups:
                for keywords in type_name_groups:
                    for entry in items:
                        if entry["path"] in used:
                            continue
                        tn = entry["type_name"]
                        if exclude_type_names and any(ex in tn for ex in exclude_type_names):
                            continue
                        if any(keyword in tn for keyword in keywords):
                            return entry["path"]
            if keyword_groups:
                for keywords in keyword_groups:
                    for entry in items:
                        if entry["path"] in used:
                            continue
                        tn = entry["type_name"]
                        if exclude_type_names and any(ex in tn for ex in exclude_type_names):
                            continue
                        haystack = f"{entry.get('original_name', '')} {entry['path'].rsplit('/', 1)[-1]}"
                        if any(keyword in haystack for keyword in keywords):
                            return entry["path"]
            # 仅当未指定任何关键词组时，才兜底返回第一个未使用文件
            if not type_name_groups and not keyword_groups:
                for entry in items:
                    if entry["path"] not in used:
                        return entry["path"]
            return None

        def _pick_evidence() -> list[str]:  # pragma: no cover
            evidence: list[str] = []
            for entry in items:
                if entry["path"] in used:
                    continue
                if any(kw in entry["type_name"] for kw in ["证据", "明细", "清单"]):
                    evidence.append(entry["path"])
            if not evidence:
                for entry in items:
                    if entry["path"] in used:
                        continue
                    haystack = f"{entry.get('original_name', '')} {entry['path'].rsplit('/', 1)[-1]}"
                    if any(kw in haystack for kw in ["证据", "明细", "清单"]):
                        evidence.append(entry["path"])
            return evidence

        file_inputs = self.page.locator("input[type='file']")
        total_inputs = min(file_inputs.count(), 10)
        for i in range(total_inputs):
            current = file_inputs.nth(i)
            try:
                label_text = str(
                    self.page.evaluate(
                        r"""(el) => {
                            const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = norm(node.innerText || '');
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        current.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            chosen_files: list[str] = []
            if "保全申请" in label_text:
                picked = _pick_path(
                    [["财产保全申请书", "保全申请书"], ["申请书"]],
                    type_name_groups=[["保全申请", "保全", "保全申请书及保函"]],
                )
                if picked:
                    chosen_files = [picked]
            elif "起诉" in label_text:
                picked = _pick_path(
                    [["起诉状", "起诉书"], ["起诉"]],
                    type_name_groups=[["起诉状"]],
                )
                if picked:
                    chosen_files = [picked]
            elif "受理" in label_text or "立案" in label_text:
                picked = _pick_path([["受理案件通知书", "受理通知书", "立案受理通知书", "立案通知书", "立案通知"]])
                if picked:
                    chosen_files = [picked]
            elif "案件证据" in label_text:
                evidence_files = _pick_evidence()
                if evidence_files:
                    chosen_files = evidence_files
            elif "申请人-" in label_text or "被申请人-" in label_text or "身份证明" in label_text:
                if "申请人-" in label_text and "-法人" in label_text:
                    applicant_license = _pick_path(
                        [["营业执照"]],
                        type_name_groups=[["营业执照", "身份证明"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    applicant_legal_id = _pick_path(
                        [["法定代表人身份证明", "身份证明书", "法人身份证明", "身份证"]],
                        type_name_groups=[["身份证明", "法定代表人"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    chosen_files = [path for path in [applicant_license, applicant_legal_id] if path]
                elif "被申请人-" in label_text and "-法人" in label_text:
                    respondent_license = _pick_path(
                        [["营业执照"]],
                        type_name_groups=[["营业执照", "身份证明"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    respondent_legal_id = _pick_path(
                        [["法定代表人身份证明", "身份证明书", "法人身份证明", "身份证"]],
                        type_name_groups=[["身份证明", "法定代表人"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    chosen_files = [path for path in [respondent_license, respondent_legal_id] if path]
                elif "被申请人-" in label_text and "-自然人" in label_text:
                    respondent_name = ""
                    match = re.search(r"被申请人-(.*?)-自然人", label_text)
                    if match:
                        respondent_name = str(match.group(1) or "").strip()

                    natural_identity = ""
                    for entry in items:
                        if entry["path"] in used:
                            continue
                        display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                        if "法定代表人" in display_name:
                            continue
                        if "身份证" not in display_name and "身份证明" not in display_name:
                            continue
                        if respondent_name and respondent_name not in display_name:
                            continue
                        natural_identity = entry["path"]
                        break

                    if natural_identity:
                        chosen_files = [natural_identity]
                else:
                    picked = _pick_path(
                        [["身份证明", "身份证"], ["营业执照"], ["授权委托书", "所函"]],
                        type_name_groups=[["身份证明", "当事人身份证明"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    if picked:
                        chosen_files = [picked]
            elif "代理人" in label_text:
                picked = _pick_path(
                    [["所函", "授权委托书", "律师证", "执业证"], ["身份证明", "身份证"]],
                    type_name_groups=[["委托材料", "委托手续", "授权委托", "所函", "律师"]],
                )
                if picked:
                    chosen_files = [picked]
            elif "证据" in label_text:
                evidence_files2 = _pick_evidence()
                if evidence_files2:
                    chosen_files = evidence_files2
            elif "其他" in label_text:
                picked = _pick_path([["其他", "保函", "担保函"]])
                if picked:
                    chosen_files = [picked]
            else:
                picked = _pick_path([[]])
                if picked:
                    chosen_files = [picked]

            if not chosen_files:
                continue

            upload_payload = self._build_file_payloads(chosen_files)
            try:
                current.set_input_files(upload_payload)
                used.update(chosen_files)
                result["uploaded"] = int(result["uploaded"]) + 1
                if len(chosen_files) > 1:
                    result["uploads"].append(
                        {
                            "index": i,
                            "label": label_text[:80],
                            "files": [path.rsplit("/", 1)[-1] for path in chosen_files],
                        }
                    )
                else:
                    result["uploads"].append(
                        {"index": i, "label": label_text[:80], "file": chosen_files[0].rsplit("/", 1)[-1]}
                    )
                self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                self._random_wait(1.8, 2.8)  # type: ignore[attr-defined]
            except Exception:
                continue

        complaint_path = next(
            (
                entry["path"]
                for entry in items
                if any(
                    kw in (entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1])
                    for kw in ("起诉状", "起诉书", "起诉")
                )
            ),
            items[0]["path"] if items else "",
        )

        for _ in range(12):
            self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
            result["next_clicked"] = self._click_first_enabled_button(["下一步", "保存并下一步"])  # type: ignore[attr-defined]
            self._random_wait(1.4, 2.2)  # type: ignore[attr-defined]
            if "gFour" in self.page.url or "gFive" in self.page.url:
                break

            errors = self._get_visible_form_errors()  # type: ignore[attr-defined]
            if any("请上传起诉" in err for err in errors):
                for j in range(total_inputs):
                    candidate = file_inputs.nth(j)
                    try:
                        label_text = str(
                            self.page.evaluate(
                                r"""(el) => {
                                    let node = el;
                                    for (let depth = 0; depth < 8 && node; depth += 1) {
                                        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                        if (text) return text;
                                        node = node.parentElement;
                                    }
                                    return '';
                                }""",
                                candidate.element_handle(),
                            )
                            or ""
                        )
                    except Exception:
                        label_text = ""
                    if "起诉" not in label_text:
                        continue
                    try:
                        candidate.set_input_files(self._build_file_payload(complaint_path))
                        result["uploads"].append(
                            {
                                "index": j,
                                "label": label_text[:80],
                                "file": complaint_path.rsplit("/", 1)[-1],
                                "retry": True,
                            }
                        )
                        self._random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                    except (TypeError, ValueError):
                        continue

            if any("身份证明材料" in err for err in errors):
                identity_paths: list[str] = []
                legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
                business_license = _pick_path([["营业执照"]])
                if legal_identity:
                    identity_paths.append(legal_identity)
                if business_license and business_license not in identity_paths:
                    identity_paths.append(business_license)

                target_hints: list[str] = []
                for err in errors:
                    match = re.search(r"请上传【(.+?)】的身份证明材料", err)
                    if not match:
                        continue
                    hint = str(match.group(1) or "").strip()
                    if hint and hint not in target_hints:
                        target_hints.append(hint)

                if identity_paths:
                    for j in range(total_inputs):
                        candidate = file_inputs.nth(j)
                        try:
                            label_text = str(
                                self.page.evaluate(
                                    r"""(el) => {
                                        let node = el;
                                        for (let depth = 0; depth < 8 && node; depth += 1) {
                                            const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                            if (text) return text;
                                            node = node.parentElement;
                                        }
                                        return '';
                                    }""",
                                    candidate.element_handle(),
                                )
                                or ""
                            )
                        except Exception:
                            label_text = ""
                        if "身份证明" not in label_text:
                            continue
                        if target_hints and not any(hint in label_text for hint in target_hints):
                            continue
                        try:
                            candidate.set_input_files(self._build_file_payloads(identity_paths))
                            result["uploads"].append(
                                {
                                    "index": j,
                                    "label": label_text[:80],
                                    "files": [path.rsplit("/", 1)[-1] for path in identity_paths],
                                    "retry": True,
                                    "reason": "identity_material",
                                }
                            )
                            self._random_wait(2.0, 2.8)  # type: ignore[attr-defined]
                        except Exception:
                            for single_path in identity_paths:
                                try:
                                    candidate.set_input_files(self._build_file_payload(single_path))
                                    result["uploads"].append(
                                        {
                                            "index": j,
                                            "label": label_text[:80],
                                            "file": single_path.rsplit("/", 1)[-1],
                                            "retry": True,
                                            "reason": "identity_material_fallback",
                                        }
                                    )
                                    self._random_wait(1.6, 2.2)  # type: ignore[attr-defined]
                                    break
                                except (TypeError, ValueError):
                                    continue

            if any("请上传" in err or "正在进行上传" in err or "当前正在进行上传操作" in err for err in errors):
                self._wait_upload_idle(timeout_ms=120000)  # type: ignore[attr-defined]
                self._random_wait(2.2, 3.2)  # type: ignore[attr-defined]

        final_upload_errors = self._get_visible_form_errors()  # type: ignore[attr-defined]
        if any("身份证明材料" in err for err in final_upload_errors):
            legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
            business_license = _pick_path([["营业执照"]])
            retry_files: list[str] = []
            if legal_identity:
                retry_files.append(legal_identity)
            if business_license and business_license not in retry_files:
                retry_files.append(business_license)

            if retry_files:
                for j in range(total_inputs):
                    candidate = file_inputs.nth(j)
                    try:
                        label_text = str(
                            self.page.evaluate(
                                r"""(el) => {
                                    let node = el;
                                    for (let depth = 0; depth < 8 && node; depth += 1) {
                                        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                        if (text) return text;
                                        node = node.parentElement;
                                    }
                                    return '';
                                }""",
                                candidate.element_handle(),
                            )
                            or ""
                        )
                    except Exception:
                        label_text = ""

                    if "申请人-" not in label_text or "-法人" not in label_text:
                        continue

                    try:
                        candidate.set_input_files(self._build_file_payloads(retry_files))
                        result["uploads"].append(
                            {
                                "index": j,
                                "label": label_text[:80],
                                "files": [path.rsplit("/", 1)[-1] for path in retry_files],
                                "retry": True,
                                "reason": "identity_material_final_retry",
                            }
                        )
                    except Exception:
                        for single_path in retry_files:
                            try:
                                candidate.set_input_files(self._build_file_payload(single_path))
                                result["uploads"].append(
                                    {
                                        "index": j,
                                        "label": label_text[:80],
                                        "file": single_path.rsplit("/", 1)[-1],
                                        "retry": True,
                                        "reason": "identity_material_final_retry_single",
                                    }
                                )
                                break
                            except (TypeError, ValueError):
                                continue

                for _ in range(4):
                    result["next_clicked"] = self._click_first_enabled_button(["下一步", "保存并下一步"])  # type: ignore[attr-defined]
                    self._random_wait(1.2, 1.8)  # type: ignore[attr-defined]
                    if "gFour" in self.page.url or "gFive" in self.page.url:
                        break

        return result

    def _retry_identity_material_upload_in_g_three(self) -> bool:  # pragma: no cover
        def _pick_path(keyword_groups: list[list[str]]) -> str | None:  # pragma: no cover
            for keywords in keyword_groups:
                for entry in self._material_items:
                    display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                    if any(keyword in display_name for keyword in keywords):
                        return entry["path"]
            return None

        legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
        business_license = _pick_path([["营业执照"]])
        retry_files: list[str] = []
        if legal_identity:
            retry_files.append(legal_identity)
        if business_license and business_license not in retry_files:
            retry_files.append(business_license)
        if not retry_files:
            return False

        uploaded = False
        file_inputs = self.page.locator("input[type='file']")
        for i in range(file_inputs.count()):
            candidate = file_inputs.nth(i)
            try:
                label_text = str(
                    self.page.evaluate(
                        r"""(el) => {
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        candidate.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            if "申请人-" not in label_text or "-法人" not in label_text:
                continue

            try:
                candidate.set_input_files(self._build_file_payloads(retry_files))
                uploaded = True
                self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                self._random_wait(2.0, 2.8)  # type: ignore[attr-defined]
            except Exception:
                for single_path in retry_files:
                    try:
                        candidate.set_input_files(self._build_file_payload(single_path))
                        uploaded = True
                        self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                        self._random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                        break
                    except Exception:
                        continue

        return uploaded

    def _retry_evidence_material_upload_in_g_three(self) -> bool:  # pragma: no cover
        evidence_files: list[str] = []
        for entry in self._material_items:
            if any(kw in entry["type_name"] for kw in ["证据", "明细", "清单"]):
                evidence_files.append(entry["path"])
        if not evidence_files:
            for entry in self._material_items:
                display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                if any(kw in display_name for kw in ["证据", "明细", "清单"]):
                    evidence_files.append(entry["path"])

        if not evidence_files:
            for entry in self._material_items:
                evidence_files.append(entry["path"])
                if len(evidence_files) >= 3:
                    break

        if not evidence_files:
            return False

        uploaded = False
        file_inputs = self.page.locator("input[type='file']")
        for i in range(file_inputs.count()):
            candidate = file_inputs.nth(i)
            try:
                label_text = str(
                    self.page.evaluate(
                        r"""(el) => {
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        candidate.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            if "证据" not in label_text:
                continue

            try:
                candidate.set_input_files(self._build_file_payloads(evidence_files))
                uploaded = True
                self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                self._random_wait(2.0, 2.8)  # type: ignore[attr-defined]
            except Exception:
                for single_path in evidence_files:
                    try:
                        candidate.set_input_files(self._build_file_payload(single_path))
                        uploaded = True
                        self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                        self._random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                        break
                    except Exception:
                        continue

        return uploaded

    # ── async counterparts ───────────────────────────────────────────

    async def _async_complete_g_three(self, case_data: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        result: dict[str, Any] = {"uploaded": 0, "next_clicked": None, "uploads": []}
        raw_paths = case_data.get("material_paths") or []
        items: list[dict[str, str]] = []
        for item in raw_paths:
            if isinstance(item, dict):
                p = str(item.get("path") or "")
                if p:
                    items.append(
                        {
                            "path": p,
                            "type_name": str(item.get("type_name") or ""),
                            "original_name": str(item.get("original_name") or ""),
                        }
                    )
            else:
                p = str(item)
                if p:
                    items.append({"path": p, "type_name": "", "original_name": ""})
        if not items:
            return result

        used: set[str] = set()

        def _pick_path(  # pragma: no cover
            keyword_groups: list[list[str]],
            *,
            type_name_groups: list[list[str]] | None = None,
            exclude_type_names: list[str] | None = None,
        ) -> str | None:
            if type_name_groups:
                for keywords in type_name_groups:
                    for entry in items:
                        if entry["path"] in used:
                            continue
                        tn = entry["type_name"]
                        if exclude_type_names and any(ex in tn for ex in exclude_type_names):
                            continue
                        if any(keyword in tn for keyword in keywords):
                            return entry["path"]
            if keyword_groups:
                for keywords in keyword_groups:
                    for entry in items:
                        if entry["path"] in used:
                            continue
                        tn = entry["type_name"]
                        if exclude_type_names and any(ex in tn for ex in exclude_type_names):
                            continue
                        haystack = f"{entry.get('original_name', '')} {entry['path'].rsplit('/', 1)[-1]}"
                        if any(keyword in haystack for keyword in keywords):
                            return entry["path"]
            if not type_name_groups and not keyword_groups:
                for entry in items:
                    if entry["path"] not in used:
                        return entry["path"]
            return None

        def _pick_evidence() -> list[str]:  # pragma: no cover
            evidence: list[str] = []
            for entry in items:
                if entry["path"] in used:
                    continue
                if any(kw in entry["type_name"] for kw in ["证据", "明细", "清单"]):
                    evidence.append(entry["path"])
            if not evidence:
                for entry in items:
                    if entry["path"] in used:
                        continue
                    haystack = f"{entry.get('original_name', '')} {entry['path'].rsplit('/', 1)[-1]}"
                    if any(kw in haystack for kw in ["证据", "明细", "清单"]):
                        evidence.append(entry["path"])
            return evidence

        file_inputs = self.page.locator("input[type='file']")
        total_inputs = min(await file_inputs.count(), 10)
        for i in range(total_inputs):
            current = file_inputs.nth(i)
            try:
                label_text = str(
                    await self.page.evaluate(
                        r"""(el) => {
                            const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = norm(node.innerText || '');
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        await current.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            chosen_files: list[str] = []
            if "保全申请" in label_text:
                picked = _pick_path(
                    [["财产保全申请书", "保全申请书"], ["申请书"]],
                    type_name_groups=[["保全申请", "保全", "保全申请书及保函"]],
                )
                if picked:
                    chosen_files = [picked]
            elif "起诉" in label_text:
                picked = _pick_path(
                    [["起诉状", "起诉书"], ["起诉"]],
                    type_name_groups=[["起诉状"]],
                )
                if picked:
                    chosen_files = [picked]
            elif "受理" in label_text or "立案" in label_text:
                picked = _pick_path([["受理案件通知书", "受理通知书", "立案受理通知书", "立案通知书", "立案通知"]])
                if picked:
                    chosen_files = [picked]
            elif "案件证据" in label_text:
                evidence_files = _pick_evidence()
                if evidence_files:
                    chosen_files = evidence_files
            elif "申请人-" in label_text or "被申请人-" in label_text or "身份证明" in label_text:
                if "申请人-" in label_text and "-法人" in label_text:
                    applicant_license = _pick_path(
                        [["营业执照"]],
                        type_name_groups=[["营业执照", "身份证明"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    applicant_legal_id = _pick_path(
                        [["法定代表人身份证明", "身份证明书", "法人身份证明", "身份证"]],
                        type_name_groups=[["身份证明", "法定代表人"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    chosen_files = [path for path in [applicant_license, applicant_legal_id] if path]
                elif "被申请人-" in label_text and "-法人" in label_text:
                    respondent_license = _pick_path(
                        [["营业执照"]],
                        type_name_groups=[["营业执照", "身份证明"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    respondent_legal_id = _pick_path(
                        [["法定代表人身份证明", "身份证明书", "法人身份证明", "身份证"]],
                        type_name_groups=[["身份证明", "法定代表人"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    chosen_files = [path for path in [respondent_license, respondent_legal_id] if path]
                elif "被申请人-" in label_text and "-自然人" in label_text:
                    respondent_name = ""
                    match = re.search(r"被申请人-(.*?)-自然人", label_text)
                    if match:
                        respondent_name = str(match.group(1) or "").strip()

                    natural_identity = ""
                    for entry in items:
                        if entry["path"] in used:
                            continue
                        display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                        if "法定代表人" in display_name:
                            continue
                        if "身份证" not in display_name and "身份证明" not in display_name:
                            continue
                        if respondent_name and respondent_name not in display_name:
                            continue
                        natural_identity = entry["path"]
                        break

                    if natural_identity:
                        chosen_files = [natural_identity]
                else:
                    picked = _pick_path(
                        [["身份证明", "身份证"], ["营业执照"], ["授权委托书", "所函"]],
                        type_name_groups=[["身份证明", "当事人身份证明"]],
                        exclude_type_names=["委托材料", "委托手续", "授权委托"],
                    )
                    if picked:
                        chosen_files = [picked]
            elif "代理人" in label_text:
                picked = _pick_path(
                    [["所函", "授权委托书", "律师证", "执业证"], ["身份证明", "身份证"]],
                    type_name_groups=[["委托材料", "委托手续", "授权委托", "所函", "律师"]],
                )
                if picked:
                    chosen_files = [picked]
            elif "证据" in label_text:
                evidence_files2 = _pick_evidence()
                if evidence_files2:
                    chosen_files = evidence_files2
            elif "其他" in label_text:
                picked = _pick_path([["其他", "保函", "担保函"]])
                if picked:
                    chosen_files = [picked]
            else:
                picked = _pick_path([[]])
                if picked:
                    chosen_files = [picked]

            if not chosen_files:
                continue

            upload_payload = self._build_file_payloads(chosen_files)
            try:
                await current.set_input_files(upload_payload)
                used.update(chosen_files)
                result["uploaded"] = int(result["uploaded"]) + 1
                if len(chosen_files) > 1:
                    result["uploads"].append(
                        {
                            "index": i,
                            "label": label_text[:80],
                            "files": [path.rsplit("/", 1)[-1] for path in chosen_files],
                        }
                    )
                else:
                    result["uploads"].append(
                        {"index": i, "label": label_text[:80], "file": chosen_files[0].rsplit("/", 1)[-1]}
                    )
                await self._async_wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                await self._async_random_wait(1.8, 2.8)  # type: ignore[attr-defined]
            except Exception:
                continue

        complaint_path = next(
            (
                entry["path"]
                for entry in items
                if any(
                    kw in (entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1])
                    for kw in ("起诉状", "起诉书", "起诉")
                )
            ),
            items[0]["path"] if items else "",
        )

        for _ in range(12):
            await self._async_wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
            result["next_clicked"] = await self._async_click_first_enabled_button(["下一步", "保存并下一步"])  # type: ignore[attr-defined]
            await self._async_random_wait(1.4, 2.2)  # type: ignore[attr-defined]
            if "gFour" in self.page.url or "gFive" in self.page.url:
                break

            errors = await self._async_get_visible_form_errors()  # type: ignore[attr-defined]
            if any("请上传起诉" in err for err in errors):
                for j in range(total_inputs):
                    candidate = file_inputs.nth(j)
                    try:
                        label_text = str(
                            await self.page.evaluate(
                                r"""(el) => {
                                    let node = el;
                                    for (let depth = 0; depth < 8 && node; depth += 1) {
                                        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                        if (text) return text;
                                        node = node.parentElement;
                                    }
                                    return '';
                                }""",
                                await candidate.element_handle(),
                            )
                            or ""
                        )
                    except Exception:
                        label_text = ""
                    if "起诉" not in label_text:
                        continue
                    try:
                        await candidate.set_input_files(self._build_file_payload(complaint_path))
                        result["uploads"].append(
                            {
                                "index": j,
                                "label": label_text[:80],
                                "file": complaint_path.rsplit("/", 1)[-1],
                                "retry": True,
                            }
                        )
                        await self._async_random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                    except (TypeError, ValueError):
                        continue

            if any("身份证明材料" in err for err in errors):
                identity_paths: list[str] = []
                legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
                business_license = _pick_path([["营业执照"]])
                if legal_identity:
                    identity_paths.append(legal_identity)
                if business_license and business_license not in identity_paths:
                    identity_paths.append(business_license)

                target_hints: list[str] = []
                for err in errors:
                    match = re.search(r"请上传【(.+?)】的身份证明材料", err)
                    if not match:
                        continue
                    hint = str(match.group(1) or "").strip()
                    if hint and hint not in target_hints:
                        target_hints.append(hint)

                if identity_paths:
                    for j in range(total_inputs):
                        candidate = file_inputs.nth(j)
                        try:
                            label_text = str(
                                await self.page.evaluate(
                                    r"""(el) => {
                                        let node = el;
                                        for (let depth = 0; depth < 8 && node; depth += 1) {
                                            const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                            if (text) return text;
                                            node = node.parentElement;
                                        }
                                        return '';
                                    }""",
                                    await candidate.element_handle(),
                                )
                                or ""
                            )
                        except Exception:
                            label_text = ""
                        if "身份证明" not in label_text:
                            continue
                        if target_hints and not any(hint in label_text for hint in target_hints):
                            continue
                        try:
                            await candidate.set_input_files(self._build_file_payloads(identity_paths))
                            result["uploads"].append(
                                {
                                    "index": j,
                                    "label": label_text[:80],
                                    "files": [path.rsplit("/", 1)[-1] for path in identity_paths],
                                    "retry": True,
                                    "reason": "identity_material",
                                }
                            )
                            await self._async_random_wait(2.0, 2.8)  # type: ignore[attr-defined]
                        except Exception:
                            for single_path in identity_paths:
                                try:
                                    await candidate.set_input_files(self._build_file_payload(single_path))
                                    result["uploads"].append(
                                        {
                                            "index": j,
                                            "label": label_text[:80],
                                            "file": single_path.rsplit("/", 1)[-1],
                                            "retry": True,
                                            "reason": "identity_material_fallback",
                                        }
                                    )
                                    await self._async_random_wait(1.6, 2.2)  # type: ignore[attr-defined]
                                    break
                                except (TypeError, ValueError):
                                    continue

            if any("请上传" in err or "正在进行上传" in err or "当前正在进行上传操作" in err for err in errors):
                await self._async_wait_upload_idle(timeout_ms=120000)  # type: ignore[attr-defined]
                await self._async_random_wait(2.2, 3.2)  # type: ignore[attr-defined]

        final_upload_errors = await self._async_get_visible_form_errors()  # type: ignore[attr-defined]
        if any("身份证明材料" in err for err in final_upload_errors):
            legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
            business_license = _pick_path([["营业执照"]])
            retry_files: list[str] = []
            if legal_identity:
                retry_files.append(legal_identity)
            if business_license and business_license not in retry_files:
                retry_files.append(business_license)

            if retry_files:
                for j in range(total_inputs):
                    candidate = file_inputs.nth(j)
                    try:
                        label_text = str(
                            await self.page.evaluate(
                                r"""(el) => {
                                    let node = el;
                                    for (let depth = 0; depth < 8 && node; depth += 1) {
                                        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                        if (text) return text;
                                        node = node.parentElement;
                                    }
                                    return '';
                                }""",
                                await candidate.element_handle(),
                            )
                            or ""
                        )
                    except Exception:
                        label_text = ""

                    if "申请人-" not in label_text or "-法人" not in label_text:
                        continue

                    try:
                        await candidate.set_input_files(self._build_file_payloads(retry_files))
                        result["uploads"].append(
                            {
                                "index": j,
                                "label": label_text[:80],
                                "files": [path.rsplit("/", 1)[-1] for path in retry_files],
                                "retry": True,
                                "reason": "identity_material_final_retry",
                            }
                        )
                    except Exception:
                        for single_path in retry_files:
                            try:
                                await candidate.set_input_files(self._build_file_payload(single_path))
                                result["uploads"].append(
                                    {
                                        "index": j,
                                        "label": label_text[:80],
                                        "file": single_path.rsplit("/", 1)[-1],
                                        "retry": True,
                                        "reason": "identity_material_final_retry_single",
                                    }
                                )
                                break
                            except (TypeError, ValueError):
                                continue

                for _ in range(4):
                    result["next_clicked"] = await self._async_click_first_enabled_button(["下一步", "保存并下一步"])  # type: ignore[attr-defined]
                    await self._async_random_wait(1.2, 1.8)  # type: ignore[attr-defined]
                    if "gFour" in self.page.url or "gFive" in self.page.url:
                        break

        return result

    async def _async_retry_identity_material_upload_in_g_three(self) -> bool:  # pragma: no cover
        def _pick_path(keyword_groups: list[list[str]]) -> str | None:  # pragma: no cover
            for keywords in keyword_groups:
                for entry in self._material_items:
                    display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                    if any(keyword in display_name for keyword in keywords):
                        return entry["path"]
            return None

        legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
        business_license = _pick_path([["营业执照"]])
        retry_files: list[str] = []
        if legal_identity:
            retry_files.append(legal_identity)
        if business_license and business_license not in retry_files:
            retry_files.append(business_license)
        if not retry_files:
            return False

        uploaded = False
        file_inputs = self.page.locator("input[type='file']")
        count = await file_inputs.count()
        for i in range(count):
            candidate = file_inputs.nth(i)
            try:
                label_text = str(
                    await self.page.evaluate(
                        r"""(el) => {
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        await candidate.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            if "申请人-" not in label_text or "-法人" not in label_text:
                continue

            try:
                await candidate.set_input_files(self._build_file_payloads(retry_files))
                uploaded = True
                await self._async_wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                await self._async_random_wait(2.0, 2.8)  # type: ignore[attr-defined]
            except Exception:
                for single_path in retry_files:
                    try:
                        await candidate.set_input_files(self._build_file_payload(single_path))
                        uploaded = True
                        await self._async_wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                        await self._async_random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                        break
                    except Exception:
                        continue

        return uploaded

    async def _async_retry_evidence_material_upload_in_g_three(self) -> bool:  # pragma: no cover
        evidence_files: list[str] = []
        for entry in self._material_items:
            if any(kw in entry["type_name"] for kw in ["证据", "明细", "清单"]):
                evidence_files.append(entry["path"])
        if not evidence_files:
            for entry in self._material_items:
                display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                if any(kw in display_name for kw in ["证据", "明细", "清单"]):
                    evidence_files.append(entry["path"])

        if not evidence_files:
            for entry in self._material_items:
                evidence_files.append(entry["path"])
                if len(evidence_files) >= 3:
                    break

        if not evidence_files:
            return False

        uploaded = False
        file_inputs = self.page.locator("input[type='file']")
        count = await file_inputs.count()
        for i in range(count):
            candidate = file_inputs.nth(i)
            try:
                label_text = str(
                    await self.page.evaluate(
                        r"""(el) => {
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        await candidate.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            if "证据" not in label_text:
                continue

            try:
                await candidate.set_input_files(self._build_file_payloads(evidence_files))
                uploaded = True
                await self._async_wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                await self._async_random_wait(2.0, 2.8)  # type: ignore[attr-defined]
            except Exception:
                for single_path in evidence_files:
                    try:
                        await candidate.set_input_files(self._build_file_payload(single_path))
                        uploaded = True
                        await self._async_wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                        await self._async_random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                        break
                    except Exception:
                        continue

        return uploaded
        evidence_files: list[str] = []
        for entry in self._material_items:
            if any(kw in entry["type_name"] for kw in ["证据", "明细", "清单"]):
                evidence_files.append(entry["path"])
        if not evidence_files:
            for entry in self._material_items:
                display_name = entry.get("original_name", "") or entry["path"].rsplit("/", 1)[-1]
                if any(kw in display_name for kw in ["证据", "明细", "清单"]):
                    evidence_files.append(entry["path"])

        if not evidence_files:
            for entry in self._material_items:
                evidence_files.append(entry["path"])
                if len(evidence_files) >= 3:
                    break

        if not evidence_files:
            return False

        uploaded = False
        file_inputs = self.page.locator("input[type='file']")
        for i in range(file_inputs.count()):
            candidate = file_inputs.nth(i)
            try:
                label_text = str(
                    self.page.evaluate(
                        r"""(el) => {
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        candidate.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            if "证据" not in label_text:
                continue

            try:
                candidate.set_input_files(self._build_file_payloads(evidence_files))
                uploaded = True
                self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                self._random_wait(2.0, 2.8)  # type: ignore[attr-defined]
            except Exception:
                for single_path in evidence_files:
                    try:
                        candidate.set_input_files(self._build_file_payload(single_path))
                        uploaded = True
                        self._wait_upload_idle(timeout_ms=90000)  # type: ignore[attr-defined]
                        self._random_wait(1.8, 2.4)  # type: ignore[attr-defined]
                        break
                    except Exception:
                        continue

        return uploaded
