"""Compile collected approval facts, without upgrading them to current approvals."""
import argparse
import hashlib
import json
from pathlib import Path

from pesticides import Catalog, DEFAULT_CATALOG, Label, Registration, Source, Use


def compile_catalog(research_path, evidence_dir):
    content = Path(research_path).read_bytes()
    research = json.loads(content)
    if research.get("schema") != "pesticide_registration_research_v1" or research.get("research_only") is not True:
        raise ValueError("仅接受已整理的公告研究资料")
    manifest = {}
    for item in research["sources"]:
        filename = item["filename"]
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError("不接受来源附件路径")
        evidence = (Path(evidence_dir) / filename).read_bytes()
        if hashlib.sha256(evidence).hexdigest() != item["sha256"] or len(evidence) != item["bytes"]:
            raise ValueError("来源附件的哈希或长度不符")
        # URL validation is also applied to every per-record source below.
        manifest[item["url"]] = item["sha256"]
    records = []
    for r in research["records"]:
        if r["current_registration_status"] != "unknown" or r["registration_valid_until"] is not None:
            raise ValueError("不能由批准公告推定当前有效状态或到期日")
        if r["review_status"] != "official_publication_transcribed_pending_agronomic_and_current_registry_review":
            raise ValueError("不能自动提升农技审校状态")
        sources = r["sources"]
        for url_key, hash_key in [("registration_table_url", "table_sha256"), ("label_url", "label_sha256")]:
            if manifest.get(sources[url_key]) != sources[hash_key]:
                raise ValueError("登记表或标签未对应到已核对附件")
        composition = r["composition"]
        # Preserve identity boundaries: C17271 + 5亿 must not read as C172715亿.
        if composition.startswith(r["product_name"]) and len(composition) > len(r["product_name"]):
            composition = r["product_name"] + " " + composition[len(r["product_name"]):]
        records.append(Registration(
            registration_number=r["registration_number"], product_name=r["product_name"],
            holder=r["holder"], formulation=r["formulation"], composition=composition,
            status="unknown", valid_until=None, current_checked_on=None,
            technical_material=r["technical_material"],
            uses=[Use.model_validate(u) for u in r["uses"]],
            source=Source(
                url=sources["announcement_url"], title="农业农村部农药批准公告及经核准标签",
                reviewed_on=r["approval_fact_verified_on"],
                reviewer="公告与标签转录核对；当前登记及植保审校未完成",
                label_version=sources["label_version"], evidence_kind="approval_announcement",
                label_url=sources["label_url"], label_locator=sources["label_locator"],
                attachment_sha256=sources["label_sha256"], announcement_date=r["announcement_date"],
            ),
            label=Label(
                technical_requirements_raw=r["label_requirements_raw"],
                precautions_raw=r["label_precautions_raw"],
                quality_guarantee_raw=r["label_quality_guarantee_raw"] or None,
                safe_interval_raw=r["safe_interval_raw"],
            ),
        ))
    return Catalog(schema_version=2, records=records, derived_from_sha256=hashlib.sha256(content).hexdigest())


def main():
    parser = argparse.ArgumentParser(description="导入公告范围和标签限制，保留当前状态未核实")
    parser.add_argument("research_json")
    parser.add_argument("--evidence-dir", required=True, help="包含来源清单所列原始附件的目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    try:
        catalog = compile_catalog(args.research_json, args.evidence_dir)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "导入失败：请检查研究资料、附件哈希、字段和状态，未写入输出。\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Parse and validate the whole batch before atomically replacing any file.
    pending = args.output.with_suffix(".pending")
    pending.write_text(json.dumps(catalog.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(args.output)
    print(f"已导入 {len(catalog.records)} 条公告记录；当前有效状态全部保留为未核实，不作为施药许可。")


if __name__ == "__main__":
    main()
