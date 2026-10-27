"""Deterministic registration checks against a reviewed local snapshot.

No scraping, model-generated facts or demo fallback. Snapshot membership is not
proof of current registration or product authenticity. See docs/pesticide-data.md.
"""
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, max_length=500, strict=True)]
NUMBER = re.compile(r"(?:PD|EX|LS)\d{6,12}", re.ASCII)
SOURCE_HOSTS = {"chinapesticide.org.cn", "www.chinapesticide.org.cn", "icama.org.cn", "www.icama.org.cn", "www.moa.gov.cn"}
MAX_AGE_DAYS = 30
CHINA_TIME = ZoneInfo("Asia/Shanghai")
DEFAULT_CATALOG = Path(__file__).parent / "data" / "pesticides" / "official-announcements.json"


def normalize_number(value: str) -> str:
    number = value.strip().upper()
    if not NUMBER.fullmatch(number):
        raise ValueError("请只输入完整登记证号，例如包装上的 PD 开头号码；目前支持 PD、EX、LS 编号。")
    return number


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CheckRequest(StrictModel):
    registration_number: Annotated[str, Field(max_length=40)]
    crop: Text = "小麦"
    target: Text

    @field_validator("registration_number")
    @classmethod
    def valid_number(cls, value):
        return normalize_number(value)


class Use(StrictModel):
    # Paired label rows prevent combining a crop from one row with another's pest.
    crop: Text
    target: Text
    label_dose_raw: Text | None = None
    application_method_raw: Text | None = None


class Source(StrictModel):
    url: Text
    title: Text
    reviewed_on: date
    reviewer: Text
    label_version: Text
    evidence_kind: Literal["current_registry_snapshot", "approval_announcement"] = "current_registry_snapshot"
    label_url: Text | None = None
    label_locator: Text | None = None
    announcement_date: date | None = None
    attachment_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None

    @field_validator("url", "label_url")
    @classmethod
    def official_url(cls, value):
        if value is None:
            return value
        url = urlsplit(value)
        if url.scheme != "https" or url.hostname not in SOURCE_HOSTS or url.username or url.password or url.port not in (None, 443):
            raise ValueError("来源需为允许的官方域名 HTTPS 地址")
        return value


class Label(StrictModel):
    technical_requirements_raw: str = Field(default="", max_length=10000)
    precautions_raw: str = Field(default="", max_length=10000)
    quality_guarantee_raw: Text | None = None
    safe_interval_raw: Text | None = None
    review_status: Literal["pending_agronomic_review"] = "pending_agronomic_review"


class Registration(StrictModel):
    registration_number: str
    product_name: Text
    holder: Text
    formulation: Text
    composition: Text
    status: Literal["active", "revoked", "unknown"]
    valid_until: date | None
    uses: Annotated[list[Use], Field(max_length=200)]
    source: Source
    technical_material: bool = False
    current_checked_on: date | None = None
    label: Label | None = None

    @field_validator("registration_number")
    @classmethod
    def valid_number(cls, value):
        return normalize_number(value)

    @model_validator(mode="after")
    def consistent_evidence(self):
        if self.technical_material != (self.formulation in ("原药", "母药")):
            raise ValueError("原药或母药必须明确标识，不能当作田间制剂")
        if self.technical_material and self.uses:
            raise ValueError("原药或母药不接受直接田间用途")
        if not self.technical_material and not self.uses:
            raise ValueError("制剂缺少登记用途")
        if self.source.evidence_kind == "approval_announcement":
            if self.status != "unknown" or self.valid_until is not None or self.current_checked_on is not None:
                raise ValueError("批准公告不能证明当前状态或证书到期日")
        return self


class Catalog(StrictModel):
    schema_version: Literal[1, 2]
    records: Annotated[list[Registration], Field(max_length=5000)]
    derived_from_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None

    @model_validator(mode="after")
    def unique_numbers(self):
        numbers = [r.registration_number for r in self.records]
        if len(numbers) != len(set(numbers)):
            raise ValueError("重复登记号，需人工合并核验，不能取第一条")
        if self.schema_version == 2:
            for record in self.records:
                if record.source.evidence_kind == "current_registry_snapshot" and record.status != "unknown" and record.current_checked_on is None:
                    raise ValueError("当前登记状态需要单独的核对日期")
        return self


def load_catalog(path: str) -> Catalog:
    content = Path(path).read_bytes()
    if len(content) > 5_000_000:
        raise ValueError("登记资料文件过大")
    return Catalog.model_validate_json(content)


def check_registration(request: CheckRequest, *, path=None, today=None) -> dict:
    today = today or datetime.now(CHINA_TIME).date()
    result = {
        "registration_number": request.registration_number,
        "crop": request.crop,
        "target": request.target,
        "checked_at": datetime.now(CHINA_TIME).isoformat(),
        "mode": "reviewed_local_snapshot",
        "status": "source_unavailable",
        "heading": "登记资料暂不可用，不能判断是否适用",
        "summary": "尚未配置可读取的人工核验资料。请核对官方登记信息及有效标签。",
        "checks": [],
        "source": None,
        "scope_match": "unknown",
        "use_decision": "hold_for_verification",
        "recommendation_allowed": False,
        "reason_codes": [],
        "next_steps": ["核对手中产品的完整有效标签及最新登记状态；无法核实时请农技人员协助。"],
        "label_reference": None,
        "explanation": "本功能核对有来源的登记资料，并非官方实时查询，不鉴别真伪，也不确认病因或是否需要施药。公告范围相符不等于现在可以用。登记状态、有效期、完整标签及田间条件未全部核实时，不生成剂量、混配或安全间隔期建议。",
    }
    # An explicit bad override must fail closed, never silently fall back.
    catalog_path = path if path is not None else (os.getenv("PESTICIDE_CATALOG_PATH", "").strip() or str(DEFAULT_CATALOG))
    if not catalog_path:
        return result
    try:
        catalog = load_catalog(catalog_path)
    except (OSError, ValueError):
        result["summary"] = "登记资料无法读取或未通过格式校验，请联系维护人员。不是登记号不存在。"
        return result
    record = next((r for r in catalog.records if r.registration_number == request.registration_number), None)
    if record is None:
        result.update(status="not_in_local_catalog", heading="本地资料未收录这个号码", summary="这不代表官方没有登记。请到官方查询平台核实，或提供完整标签请农技人员核对。")
        return result
    historical = record.source.evidence_kind == "approval_announcement"
    result["mode"] = "official_announcement_snapshot" if historical else "reviewed_local_snapshot"
    result["source"] = record.source.model_dump(mode="json")
    result["checks"] = [
        ["登记号", record.registration_number], ["产品名称", record.product_name],
        ["登记持有人", record.holder], ["剂型", record.formulation],
        ["有效成分及含量（资料原文）", record.composition],
        ["公告登记范围" if historical else "资料登记范围", "；".join(f"{u.crop} / {u.target}" for u in record.uses) or "仅供制剂加工，不得直接用于农作物"],
        ["资料登记状态", {"active": "有效", "revoked": "撤销", "unknown": "未确认"}[record.status]],
        ["资料有效期至", str(record.valid_until or "未确认")],
    ]
    if historical:
        result["checks"].extend([["当前有效状态", "尚未核实"], ["当前登记证到期日", "尚未核实；不能用产品质量保证期推算"]])
    if record.label:
        result["label_reference"] = {
            "version": record.source.label_version,
            "locator": record.source.label_locator,
            "url": record.source.label_url,
            "precautions_raw": record.label.precautions_raw,
            "review_status": record.label.review_status,
            "dose_visibility": "withheld",
            "note": "以下是该公告版本标签的注意事项原文，供核对限制，不是本次用药处方。当前未完成登记及植保审校，不展示制剂用量、频次或兑水量。安全间隔期未核实，不表示0天。",
        }
    unknown_target = request.target in ("还没确定", "不清楚", "未知")
    crop_match = any(u.crop == request.crop for u in record.uses)
    pair_match = any(u.crop == request.crop and u.target == request.target for u in record.uses)
    result["scope_match"] = "not_applicable" if record.technical_material else "unknown" if unknown_target and crop_match else "match" if pair_match else "mismatch"
    checked = record.current_checked_on or record.source.reviewed_on
    age = (today - checked).days
    if historical or record.status == "unknown":
        result["reason_codes"].append("current_status_unverified")
    if not record.valid_until:
        result["reason_codes"].append("expiry_unverified")
    if age < 0 or age > MAX_AGE_DAYS:
        result["reason_codes"].append("evidence_date_needs_review")
    if record.technical_material:
        result.update(status="mismatch", use_decision="do_not_apply_from_this_record", heading="这是原药或母药登记，不能直接用于田间", summary="该登记资料用于制剂加工，不能把它当成农户可直接施用的产品。请核对手中制剂自己的登记证号。")
        result["reason_codes"].append("technical_material_not_for_field_use")
    elif record.status == "revoked" or (record.valid_until and record.valid_until < today):
        result.update(status="mismatch", heading="资料显示登记撤销或已过有效期", summary="不要依据该资料使用，请核对最新官方登记状态。")
        result.update(use_decision="do_not_apply_from_this_record")
        result["reason_codes"].append("revoked_or_expired_in_record")
    elif not crop_match:
        result.update(status="mismatch", heading="资料中的登记作物不匹配", summary="该资料没有列出当前作物，不能据此用于当前情况。")
        result.update(use_decision="do_not_apply_from_this_record")
        result["reason_codes"].append("crop_mismatch")
    elif unknown_target:
        result.update(status="needs_review", heading="先确认防治对象，再核对是否匹配", summary="登记信息不等于病因判断。请补充症状或请农技人员协助确认。")
        result["reason_codes"].append("target_unknown")
    elif not pair_match:
        result.update(status="mismatch", heading="资料中的作物与防治对象组合不匹配", summary="未找到这一作物对应的防治对象。名称不同也需人工复核，系统不会自动扩大登记范围。")
        result.update(use_decision="do_not_apply_from_this_record")
        result["reason_codes"].append("target_mismatch")
    elif age < 0 or age > MAX_AGE_DAYS:
        result.update(status="needs_review", heading="资料时间异常或超过复核期限", summary="资料超过30天未复核，或复核日期在未来，暂不据此判断适用。")
    elif historical or record.status != "active" or not record.valid_until:
        result.update(status="needs_review", heading="公告范围相符，但现在能否用还未核实", summary=f"资料中的{request.crop}与防治对象字段相符，但当前登记状态、证书有效期及标签版本未核实。暂不能据此施药。")
    else:
        result.update(status="fields_match", heading="快照中的作物和对象相符，仍需核对当前标签", summary="仅表示已核验快照的字段相符，不代表确诊、推荐用药或已完成当前官方登记核验。请核对手中产品的成分含量、剂型及完整有效标签。")
        result["reason_codes"].append("field_conditions_not_assessed")
    if result["use_decision"] == "do_not_apply_from_this_record":
        result["next_steps"] = ["不要根据这条记录将产品用于当前情况。", "核对包装登记证号及最新标签；需选药时请农技人员结合现场情况复核。"]
    else:
        result["next_steps"] = ["先核实当前登记状态、到期日及完整有效标签，再判断是否可用。", "核对手中产品的持有人、含量、剂型，并确认田间病因和发生程度；未核实前不据此施药。"]
    return result


def format_check_answer(result_json: str) -> str:
    """Render critical tool results without asking the model to change the verdict."""
    try:
        result = json.loads(result_json)
        if result.get("status") not in {"source_unavailable", "not_in_local_catalog", "needs_review", "mismatch", "fields_match"}:
            return "尚未完成登记核对，请提供包装上的完整登记证号和准备防治的对象。不得据此判断可以施药。"
        lines = [result["heading"], result["summary"]]
        lines.extend(f"{key}：{value}" for key, value in result.get("checks", []))
        lines.extend(result.get("next_steps", []))
        if result.get("source"):
            source = result["source"]
            lines.extend([f"来源：{source['url']}", f"资料核对日期：{source['reviewed_on']}；标签版本：{source['label_version']}"])
        lines.append(result.get("explanation", ""))
        return "\n\n".join(lines)
    except (ValueError, KeyError, TypeError, AttributeError):
        return "核对服务没有返回完整结果，请重新核实登记信息；暂不能据此施药。"


def check_pesticide(registration_number: str, target: str, crop: str = "小麦") -> str:
    """Agent tool wrapper: validation errors are facts too, never fabricated matches."""
    try:
        request = CheckRequest(registration_number=registration_number, target=target, crop=crop)
    except ValueError:
        return json.dumps({"status": "invalid_input", "summary": "登记号或查询字段不完整，请用户核对包装后补充。"}, ensure_ascii=False)
    return json.dumps(check_registration(request), ensure_ascii=False)
