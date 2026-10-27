"""Local lexical retrieval of observation-only, unreviewed uploaded evidence.

No vector service/model needed. Rankings are relevance, not disease probability.
The original prescription archive is deliberately outside the retrieval boundary.
"""
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field

from import_knowledge import BLOCKED, digest

DATA_DIR = Path(__file__).parent / "data" / "knowledge"
NOTICE = "来源为用户上传《小麦知识库最新版》，尚无逐条官方出处或农技审校；仅作观察与补问参考，不作为确诊、用药或登记依据。"
ALIASES = {"叶子": "叶片", "长白粉": "白色粉状物", "一层白粉": "白色粉状物", "白粉末": "白色粉状物", "腻虫": "麦蚜", "红蜘蛛": "麦蜘蛛", "黄叶": "发黄", "黄了": "发黄", "粉红霉": "粉红色霉层"}
QUESTIONS = {
    "小麦白粉病": "请看叶片正反面：有没有白色粉状物，或粉层里出现小黑点？",
    "小麦锈病": "叶片上有没有黄色或红褐色、像锈粉一样的凸起小堆？",
    "小麦赤霉病": "请看麦穗：有没有水渍状褐斑，或粉红色霉层？",
    "小麦纹枯病": "请拨开茎基部叶鞘：有没有褐色病斑或腐烂？",
    "小麦茎基腐病": "请看茎基部和根：有没有褐变或霉层？同时保留全株照片。",
    "麦蚜": "请看叶背、茎秆和穗部：有没有成群聚集的小虫？",
    "麦蜘蛛": "叶片是否有黄白色小点？请补拍小虫和叶片近景。",
    "除草剂残留": "异常出现前是否用过除草剂？请记下产品名称、时间和实际用量。",
    "药害叠加": "异常出现前是否用过药，或同时遇到低温、土壤过湿？",
}


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000, strict=True)


class AssistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=4000, strict=True)
    distribution: str = Field(default="", max_length=500, strict=True)
    stage: str = Field(default="", max_length=500, strict=True)


def terms(text):
    text = str(text).lower()
    for word, synonym in ALIASES.items():
        text = text.replace(word, synonym)
    text = re.sub(r"冬小麦|小麦|帮我|看看|请问|怎么|什么|一下", "", text)
    tokens = []
    for part in re.findall(r"[\u4e00-\u9fff]+|[a-z]+", text):
        tokens.extend(part[i:i+2] for i in range(len(part)-1))
    return Counter(tokens)


def load_corpus(directory=DATA_DIR):
    directory = Path(directory)
    corpus = json.loads((directory / "observations.json").read_text(encoding="utf-8"))
    archive = (directory / "source.txt").read_bytes()
    if corpus["schema_version"] != 1 or digest(archive) != corpus["source"]["archive_sha256"]:
        raise ValueError("资料版本或原文校验失败")
    paragraphs = dict(line.split(" ", 1) for line in archive.decode().splitlines())
    ids = set()
    for chunk in corpus["chunks"]:
        quote = chunk["quote"]
        if chunk["id"] in ids or chunk["review_status"] != "pending_review" or BLOCKED.search(quote):
            raise ValueError("条目重复、状态异常或包含限制内容")
        ids.add(chunk["id"])
        if not quote or not all(sentence in paragraphs[chunk["paragraph"]] for sentence in quote.split("。") if sentence):
            raise ValueError("引文无法定位原文")
    return corpus


def search(query: str, limit=3, *, directory=DATA_DIR):
    response = {"status": "unavailable", "method": "chinese_bigram_bm25", "notice": NOTICE, "results": [],
                "retrieved_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()}
    try:
        corpus = load_corpus(directory)
    except (OSError, ValueError, KeyError, TypeError):
        return response
    response["status"] = "no_match"
    q = terms(query)
    # Short/generic descriptions do not become an invented disease match.
    if not q:
        return response
    chunks = corpus["chunks"]
    documents = [terms(c["topic"] + " " + c["quote"] + " " + " ".join(c["keywords"])) for c in chunks]
    n = len(documents)
    avg = sum(sum(d.values()) for d in documents) / max(n, 1)
    ranked = []
    for chunk, doc in zip(chunks, documents):
        score = 0
        for word in q.keys() & doc.keys():
            frequency = sum(word in d for d in documents)
            idf = math.log(1 + (n-frequency+0.5)/(frequency+0.5))
            tf = doc[word]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * sum(doc.values()) / max(avg, 1)))
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda row: (-row[0], row[1]["id"]))
    cutoff = ranked[0][0] * 0.45 if ranked else 0
    for _, chunk in [row for row in ranked if row[0] >= cutoff][:max(1, min(int(limit), 5))]:
        response["results"].append({**chunk, "source": corpus["source"]})
    if response["results"]:
        response["status"] = "found"
    return response


def assist(description, distribution="", stage="", *, directory=DATA_DIR):
    # Growth stage/distribution are retained as user facts, not weather or a rule.
    result = search(description, directory=directory)
    result["heading"] = "找到一些相似描述，先补一个现场细节"
    result["summary"] = "仅凭当前描述不能确定病因；相似症状也可能来自缺素、冻害、药害等原因。"
    result["next_question"] = "异常最明显在叶片、茎基部、根部还是麦穗？请补拍该部位和全株照片。"
    result["choices"] = ["叶片", "茎基部或根部", "麦穗", "不清楚"]
    result["context"] = {"distribution": distribution, "stage": stage}
    if result["results"]:
        topic = result["results"][0]["topic"]
        question = next((q for key, q in QUESTIONS.items() if topic.startswith(key)), None)
        if question:
            result["next_question"] = question
            result["choices"] = ["看到了", "没看到", "还没看清"]
    else:
        result["heading"] = "暂时没有找到足够相关的资料" if result["status"] == "no_match" else "知识资料暂不可用"
    return result


def search_knowledge(query: str):
    return json.dumps(search(str(query)[:2000]), ensure_ascii=False)
