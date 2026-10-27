"""Reproducible DOCX intake. Documents are evidence, never instructions.

Only observation fields are published. Full text remains an offline audit file.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

DEFAULT_OUTPUT = Path(__file__).parent / "data" / "knowledge"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
BLOCKED = re.compile(r"补救|用药|施药|喷|拌种|兑水|防治指标|阈值|买什么|毫升|公斤|克/|毒饵|必须|必然|杀菌剂|杀虫剂|忽略|指令|system|https?://|\d+\.?\d*[%％]", re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def extract(path):
    with ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > 10_000_000:
            raise ValueError("文档过大")
        body = ET.fromstring(archive.read(info)).find("w:body", NS)
    paragraphs = []
    for i, p in enumerate(body.findall(".//w:p", NS), 1):
        text = "".join(n.text or "" for n in p.findall(".//w:t", NS)).strip()
        if text:
            paragraphs.append({"id": f"P{i:04d}", "text": text})
    return paragraphs


def build(path, output=DEFAULT_OUTPUT):
    path, output = Path(path), Path(output)
    paragraphs = extract(path)
    chunks, excluded = [], []
    section, topic, category = "", "", ""
    for p in paragraphs:
        text = p["text"]
        if re.match(r"[一二三四五六七八九十]+、", text):
            section = text
            category = "disease" if "病害知识" in text else "pest" if "主要虫害" in text else "nutrition" if "缺素" in text else "context"
            topic = ""
        if re.match(r"（[一二三四五六七八九十]+）", text):
            topic = re.sub(r"^（[^）]+）", "", text)
        # The additional factors use numeric topic headings instead.
        if re.match(r"\d+\. [^：。]+$", text) and category == "context":
            topic = re.sub(r"^\d+\. ", "", text)
        observation = None
        if category in ("disease", "pest") and re.match(r"1\. (症状|危害)：", text):
            observation = re.sub(r"^1\. (症状|危害)：", "", text)
            observation = re.split(r"什么时候打|防治指标|种子处理|低龄幼虫期用", observation)[0].rstrip("。 ") + "。"
        elif category == "nutrition" and re.match(r"\d+\. [^：]+：", text):
            topic, observation = re.sub(r"^\d+\. ", "", text).split("：", 1)
            observation = observation.split("补救：")[0].rstrip("。 ") + "。"
        elif re.match(r"（1）表现：", text):
            observation = text.split("表现：", 1)[1]
        if observation and topic:
            # Exact source sentences only. No generated rewrite of an unsafe span.
            safe_sentences = [s + "。" for s in observation.split("。") if s and not BLOCKED.search(s)]
            quote = "".join(safe_sentences)
            if quote:
                chunks.append({
                    "id": f"wheat-v1-{p['id']}", "paragraph": p["id"],
                    "section": section, "topic": topic, "category": category,
                    "quote": quote, "keywords": [], "review_status": "pending_review",
                })
        if "特征词：" in text and chunks and chunks[-1]["topic"] == topic:
            chunks[-1]["keywords"] = [k.strip("。 ") for k in text.split("特征词：", 1)[1].split("、") if not BLOCKED.search(k)]
        if BLOCKED.search(text) or re.search(r"\d+\s*[%％]|推荐品种|什么时候打|用什么药|依据/为什么|怎么补|怎么调|应对：", text):
            excluded.append(p["id"])
    archive = "\n".join(f"{p['id']} {p['text']}" for p in paragraphs) + "\n"
    source = {
        "id": "user-wheat-v1", "title": path.name,
        "imported_on": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(), "docx_sha256": digest(path.read_bytes()),
        "archive_sha256": digest(archive.encode()), "origin": "user_upload",
        "review_status": "pending_review", "official_sources_provided": False,
    }
    payload = {"schema_version": 1, "source": source, "chunks": chunks}
    audit = {"paragraph_count": len(paragraphs), "observation_chunks": len(chunks),
             "excluded_from_advice": excluded, "policy": "observation_only; no prescriptions, brands, thresholds or registration facts"}
    output.mkdir(parents=True, exist_ok=True)
    (output / "source.txt").write_text(archive, encoding="utf-8")
    (output / "observations.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "intake-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入小麦知识文档，仅发布观察描述，原文留档")
    parser.add_argument("docx")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.docx, args.output), ensure_ascii=False))
