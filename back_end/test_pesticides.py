"""Synthetic records only. Never install these as production data."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from pesticides import Catalog, CheckRequest, check_registration
from main import app
import tools


TODAY = date(2026, 10, 26)


def fixture():
    return {
        "schema_version": 1,
        "records": [{
            "registration_number": "PD20990001",
            "product_name": "虚构测试产品，不得用于农业",
            "holder": "虚构测试持有人",
            "formulation": "测试剂型", "composition": "测试成分（无实际含量）",
            "status": "active", "valid_until": "2099-01-01",
            "uses": [{"crop": "小麦", "target": "白粉病"}, {"crop": "水稻", "target": "稻飞虱"}],
            "source": {
                "url": "https://www.icama.org.cn/",
                "title": "虚构测试数据，链接仅作域名校验，非本产品证据",
                "reviewed_on": TODAY.isoformat(), "reviewer": "测试人员",
                "label_version": "测试版本",
            },
        }],
    }


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "catalog.json")
        self.data = fixture()
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        Path(self.path).write_text(json.dumps(self.data), encoding="utf-8")

    def check(self, **kwargs):
        self.write()
        req = CheckRequest(registration_number="PD20990001", target=kwargs.pop("target", "白粉病"), **kwargs)
        return check_registration(req, path=self.path, today=TODAY)

    def test_match_is_snapshot_only_no_dose(self):
        r = self.check()
        self.assertEqual(r["status"], "fields_match")
        self.assertIn("不代表确诊", r["summary"])
        self.assertIn("source", r)
        self.assertNotIn("dose", r)

    def test_normalize_and_invalid_input(self):
        self.assertEqual(CheckRequest(registration_number=" pd20990001 ", target="白粉病").registration_number, "PD20990001")
        for number in ["DEMO-WHEAT-001", "PD-20990001", "PD２０９９０００１", "PD20990001<script>", "", "123456"]:
            with self.assertRaises(ValueError):
                CheckRequest(registration_number=number, target="白粉病")

    def test_missing_source_vs_unlisted(self):
        req = CheckRequest(registration_number="PD20990002", target="白粉病")
        self.assertEqual(check_registration(req, path="")["status"], "source_unavailable")
        r = check_registration(req, path=self.path)
        self.assertEqual(r["status"], "not_in_local_catalog")
        self.assertIn("不代表", r["summary"])

    def test_cross_row_does_not_match(self):
        self.assertEqual(self.check(target="稻飞虱")["status"], "mismatch")

    def test_unknown_target_requires_review(self):
        self.assertEqual(self.check(target="还没确定")["status"], "needs_review")

    def test_crop_mismatch(self):
        self.assertEqual(self.check(crop="玉米")["status"], "mismatch")

    def test_revoked_and_expired(self):
        self.data["records"][0]["status"] = "revoked"
        self.assertEqual(self.check()["status"], "mismatch")
        self.data["records"][0]["status"] = "active"
        self.data["records"][0]["valid_until"] = "2026-10-25"
        self.assertEqual(self.check()["status"], "mismatch")

    def test_missing_validity_or_status(self):
        self.data["records"][0]["valid_until"] = None
        self.assertEqual(self.check()["status"], "needs_review")
        self.data = fixture()
        self.data["records"][0]["status"] = "unknown"
        self.assertEqual(self.check()["status"], "needs_review")

    def test_stale_future_and_boundary(self):
        for offset, expected in [(-31, "needs_review"), (1, "needs_review"), (-30, "fields_match")]:
            self.data["records"][0]["source"]["reviewed_on"] = (TODAY + timedelta(days=offset)).isoformat()
            self.assertEqual(self.check()["status"], expected)

    def test_duplicates_fail_closed(self):
        self.data["records"].append(copy.deepcopy(self.data["records"][0]))
        self.assertEqual(self.check()["status"], "source_unavailable")

    def test_nonofficial_sources_rejected(self):
        for url in ["https://example.com/", "javascript:alert(1)", "https://www.icama.org.cn.evil.test/", "https://user@www.icama.org.cn/", "http://www.icama.org.cn/"]:
            self.data["records"][0]["source"]["url"] = url
            with self.assertRaises(ValueError):
                Catalog.model_validate(self.data)

    def test_bad_file_never_returns_match(self):
        Path(self.path).write_text("{broken", encoding="utf-8")
        req = CheckRequest(registration_number="PD20990001", target="白粉病")
        self.assertEqual(check_registration(req, path=self.path)["status"], "source_unavailable")

    def test_http_endpoint_static_and_validation(self):
        client = TestClient(app)
        with patch.dict(os.environ, {"PESTICIDE_CATALOG_PATH": self.path}):
            r = client.post("/api/pesticides/check", json={"registration_number": "PD20990001", "target": "白粉病"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("checked_at", r.json())
        self.assertEqual(client.post("/api/pesticides/check", json={"registration_number": "DEMO-001", "target": "白粉病"}).status_code, 422)
        self.assertEqual(client.get("/index.html").status_code, 200)
        self.assertEqual(client.get("/health").json(), {"status": "ok"})

    def test_agent_tool_is_same_checker(self):
        with patch.dict(os.environ, {"PESTICIDE_CATALOG_PATH": "/missing-explicit-catalog.json"}):
            r = json.loads(tools.execute("check_pesticide", {"registration_number": "PD20990001", "target": "白粉病"}))
        self.assertEqual(r["status"], "source_unavailable")
        r = json.loads(tools.execute("check_pesticide", {"registration_number": "DEMO-001", "target": "白粉病"}))
        self.assertEqual(r["status"], "invalid_input")


class ImportedRegistrationTests(unittest.TestCase):
    def query(self, number, target="赤霉病", **kwargs):
        from pesticides import DEFAULT_CATALOG
        return check_registration(CheckRequest(registration_number=number, target=target, **kwargs), path=str(DEFAULT_CATALOG), today=TODAY + timedelta(days=1))

    def test_all_twenty_imported_and_never_promoted(self):
        from pesticides import DEFAULT_CATALOG, load_catalog
        catalog = load_catalog(str(DEFAULT_CATALOG))
        self.assertEqual(len(catalog.records), 20)
        self.assertEqual(sum(r.technical_material for r in catalog.records), 9)
        for r in catalog.records:
            self.assertEqual(r.status, "unknown")
            self.assertIsNone(r.valid_until)
            self.assertIsNone(r.current_checked_on)
            self.assertEqual(r.source.evidence_kind, "approval_announcement")

    def test_wheat_record_requires_current_verification_and_hides_dose(self):
        r = self.query("PD20250010")
        self.assertEqual(r["status"], "needs_review")
        self.assertEqual(r["scope_match"], "match")
        self.assertFalse(r["recommendation_allowed"])
        self.assertIn("current_status_unverified", r["reason_codes"])
        self.assertEqual(r["label_reference"]["dose_visibility"], "withheld")
        serialized = json.dumps(r, ensure_ascii=False)
        for dose in ["150-200", "7天左右", "30—50公斤", "质量保证期：1年"]:
            self.assertNotIn(dose, serialized)
        self.assertIn("C17271 5亿CFU/克", serialized)
        self.assertIn("不可和碱性物质", r["label_reference"]["precautions_raw"])

    def test_target_mismatch_not_hidden_by_unknown_status(self):
        r = self.query("PD20250010", "白粉病")
        self.assertEqual(r["status"], "mismatch")
        self.assertIn("target_mismatch", r["reason_codes"])
        self.assertEqual(r["use_decision"], "do_not_apply_from_this_record")

    def test_cucumber_powdery_mildew_is_not_wheat_registration(self):
        r = self.query("PD20250008", "白粉病")
        self.assertEqual(r["scope_match"], "mismatch")
        self.assertIn("crop_mismatch", r["reason_codes"])
        self.assertFalse(r["recommendation_allowed"])

    def test_technical_material_is_blocked(self):
        r = self.query("PD20250005")
        self.assertEqual(r["scope_match"], "not_applicable")
        self.assertIn("technical_material_not_for_field_use", r["reason_codes"])
        self.assertEqual(r["status"], "mismatch")

    def test_unknown_target_is_not_matched(self):
        r = self.query("PD20250010", "还没确定")
        self.assertEqual(r["scope_match"], "unknown")
        self.assertIn("target_unknown", r["reason_codes"])

    def test_source_is_allowed_ministry_url_and_saved_version(self):
        r = self.query("PD20250010")
        self.assertTrue(r["source"]["url"].startswith("https://www.moa.gov.cn/"))
        self.assertIn("880", r["source"]["label_version"])
        self.assertEqual(r["source"]["reviewed_on"], "2026-10-27")

    def test_imported_scope_keeps_rows_paired(self):
        r = self.query("PD20251261", "白粉病", crop="葡萄")
        self.assertEqual(r["status"], "mismatch")
        r = self.query("PD20251261", "灰霉病", crop="葡萄")
        self.assertEqual(r["scope_match"], "match")
        self.assertEqual(r["status"], "needs_review")

    def test_default_catalog_and_broken_override(self):
        req = CheckRequest(registration_number="PD20250010", target="赤霉病")
        with patch.dict(os.environ, {"PESTICIDE_CATALOG_PATH": ""}):
            self.assertEqual(check_registration(req)["scope_match"], "match")
        with patch.dict(os.environ, {"PESTICIDE_CATALOG_PATH": "/missing-overridden-catalog"}):
            self.assertEqual(check_registration(req)["status"], "source_unavailable")

    def test_approval_record_cannot_be_edited_to_active(self):
        from pesticides import DEFAULT_CATALOG
        data = json.loads(DEFAULT_CATALOG.read_text())
        data["records"][0]["status"] = "active"
        with self.assertRaises(ValueError):
            Catalog.model_validate(data)

    def test_v2_current_state_needs_separate_check_date(self):
        data = fixture()
        data["schema_version"] = 2
        with self.assertRaises(ValueError):
            Catalog.model_validate(data)
        data["records"][0]["current_checked_on"] = TODAY.isoformat()
        Catalog.model_validate(data)

    def test_recorded_storage_life_does_not_set_expiry(self):
        r = self.query("PD20250010")
        self.assertIn("expiry_unverified", r["reason_codes"])


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        data_path = Path(__file__).resolve().parents[1] / "docs/research/pesticide-registration-2026-10-27.json"
        self.data = json.loads(data_path.read_text())
        self.data["records"] = self.data["records"][:1]
        self.research_path = self.root / "research.json"

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        from import_registrations import compile_catalog
        import hashlib
        for source in self.data["sources"]:
            content = b"synthetic attachment bytes for importer tests"
            (self.root / source["filename"]).write_bytes(content)
            source["sha256"] = hashlib.sha256(content).hexdigest()
            source["bytes"] = len(content)
            for record in self.data["records"]:
                for key, sha_key in [("registration_table_url", "table_sha256"), ("label_url", "label_sha256")]:
                    if record["sources"][key] == source["url"]:
                        record["sources"][sha_key] = source["sha256"]
        self.research_path.write_text(json.dumps(self.data), encoding="utf-8")
        return compile_catalog(self.research_path, self.root)

    def test_preserves_dates_unknown_state_and_label_version(self):
        record = self.build().records[0]
        self.assertEqual(record.status, "unknown")
        self.assertIsNone(record.valid_until)
        self.assertEqual(str(record.source.reviewed_on), "2026-10-27")
        self.assertIn("880", record.source.label_version)

    def test_does_not_import_invented_current_approval(self):
        self.data["records"][0]["current_registration_status"] = "active"
        with self.assertRaises(ValueError):
            self.build()

    def test_tampered_attachment_is_rejected(self):
        from import_registrations import compile_catalog
        self.build()
        (self.root / self.data["sources"][0]["filename"]).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            compile_catalog(self.research_path, self.root)

    def test_bundled_catalog_is_derived_from_original_research(self):
        import hashlib
        from pesticides import DEFAULT_CATALOG, load_catalog
        source = Path(__file__).resolve().parents[1] / "docs/research/pesticide-registration-2026-10-27.json"
        self.assertEqual(load_catalog(str(DEFAULT_CATALOG)).derived_from_sha256, hashlib.sha256(source.read_bytes()).hexdigest())


class AgentVerdictTests(unittest.TestCase):
    def test_agent_does_not_rewrite_hold_as_usable(self):
        import agent
        call = json.dumps({"action": "tool", "tool": "check_pesticide", "args": {"registration_number": "PD20250010", "target": "赤霉病"}})
        with patch("llm.chat", side_effect=[call, "可以马上使用，每亩随便加量"] ) as model:
            with patch.dict(os.environ, {"PESTICIDE_CATALOG_PATH": ""}):
                reply = agent.run([{"role": "user", "content": "核对PD20250010用于赤霉病"}])
        self.assertEqual(model.call_count, 1)
        self.assertIn("暂不能据此施药", reply)
        self.assertNotIn("可以马上使用", reply)
        self.assertIn("www.moa.gov.cn", reply)

    def test_bad_tool_arguments_do_not_create_a_positive_reply(self):
        import agent
        call = json.dumps({"action": "tool", "tool": "check_pesticide", "args": {"registration_number": "DEMO-001", "target": "赤霉病"}})
        with patch("llm.chat", return_value=call):
            reply = agent.run([{"role": "user", "content": "核对"}])
        self.assertIn("尚未完成登记核对", reply)


if __name__ == "__main__":
    unittest.main()
