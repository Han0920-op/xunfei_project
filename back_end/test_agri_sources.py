"""Official data trust gates and regional notice lifecycle; fixtures are synthetic."""

import json, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import agri_sources as a, personal
from main import app


class OfficialSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = patch.object(personal, "PATH", Path(self.tmp.name) / "intel.db")
        self.path.start()
        self.current = datetime(2026, 11, 1, 12, tzinfo=personal.TZ)
        self.clock = patch.object(personal, "now", return_value=self.current)
        self.clock.start()
        self.client = TestClient(app)
        self.other = TestClient(app)
        self.h = {"X-Zhimai-Personal": "1"}
        for c in (self.client, self.other):
            c.get("/api/personal/session")
        self.who = self.client.cookies.get("zhimai_owner")

    def tearDown(self):
        self.clock.stop()
        self.path.stop()
        self.tmp.cleanup()

    def doc(self, identifier="d", **changes):
        d = {
            "id": identifier,
            "url": "https://www.moa.gov.cn/xw/zwdt/202611/t20261101_"
            + identifier
            + ".htm",
            "title": "测试小麦条锈病区域情报",
            "text": "观察叶片上是否有成行排列的黄色粉状物。\n不应因黄化直接认定病害。",
            "sha256": "abc",
            "publisher": "测试替身：官方结构",
            "kind": "bulletin",
            "regions": ["河南"],
            "pests": ["条锈病"],
            "published_on": "2026-11-01",
            "valid_until": "2026-11-08",
            "retrieved_at": self.current.isoformat(),
            "review_status": "metadata_reviewed",
            "agronomic_review": "pending_review",
            "review_note": "测试替身适用范围",
            "reviewed_by": "fixture",
        } | changes
        with a.db() as c:
            a.ensure(c)
            c.execute(
                "INSERT INTO official_documents VALUES(?,?,?)",
                (d["id"], d["url"], json.dumps(d, ensure_ascii=False)),
            )
        return d

    def sub(self, identifier="s", **changes):
        d = {
            "province": "河南",
            "city": "郑州",
            "pests": ["条锈病"],
            "enabled": True,
            "max_daily": 1,
            "quiet_start": "22:00",
            "quiet_end": "07:00",
        } | changes
        r = self.client.put(
            "/api/intelligence/subscriptions/" + identifier, headers=self.h, json=d
        )
        self.assertEqual(r.status_code, 200)
        return d

    def notices(self):
        return personal.listing(self.who, "notifications")

    def test_no_opt_in_no_notification_then_exact_scope_dedup_and_attribution(self):
        self.doc()
        a.deliver()
        self.assertEqual(self.notices(), [])
        self.sub()
        a.deliver()
        a.deliver()
        n = self.notices()
        self.assertEqual(len(n), 1)
        self.assertIn("不能证明", n[0]["message"])
        self.assertEqual(n[0]["source"]["published_on"], "2026-11-01")
        self.assertIn("省级", n[0]["message"])

    def test_filters_expiry_future_unreviewed_wrong_province_wrong_pest_stale_and_guideline(
        self,
    ):
        self.sub()
        for identifier, changes in [
            ("expired", {"valid_until": "2026-10-31"}),
            ("future", {"published_on": "2026-11-02"}),
            ("pending", {"review_status": "pending_metadata_review"}),
            ("region", {"regions": ["山东"]}),
            ("pest", {"pests": ["蚜虫"]}),
            ("stale", {"retrieved_at": (self.current - timedelta(days=2)).isoformat()}),
            ("guideline", {"kind": "guideline"}),
        ]:
            self.doc(identifier, **changes)
        a.deliver()
        self.assertEqual(self.notices(), [])

    def test_quiet_crosses_midnight_then_defers_until_end_and_no_expired_backfill(self):
        self.doc()
        self.sub()
        for hour in (23, 1, 6):
            with patch.object(
                personal, "now", return_value=self.current.replace(hour=hour)
            ):
                a.deliver()
        self.assertEqual(self.notices(), [])
        a.deliver()
        self.assertEqual(len(self.notices()), 1)

    def test_frequency_owner_wide_dedup_across_subscriptions_unsubscribe_and_pause(
        self,
    ):
        self.doc("d1")
        self.doc("d2")
        self.sub()
        self.sub("s2")
        a.deliver()
        self.assertEqual(len(self.notices()), 1)
        self.sub(enabled=False)
        self.client.delete("/api/intelligence/subscriptions/s2", headers=self.h)
        self.doc("d3")
        a.deliver()
        self.assertEqual(len(self.notices()), 1)
        # Different matching subscriptions never redeliver the same document.
        self.sub(max_daily=3)
        a.deliver()
        self.assertEqual(len(self.notices()), 3)
        self.sub("third", max_daily=3)
        a.deliver()
        self.assertEqual(len(self.notices()), 3)

    def test_city_limited_bulletin_does_not_match_other_city_or_unspecified_city(self):
        self.doc(cities=["濮阳"])
        self.sub(city="郑州")
        a.deliver()
        self.assertEqual(self.notices(), [])
        self.sub(city="")
        a.deliver()
        self.assertEqual(self.notices(), [])
        self.sub(city="濮阳市")
        a.deliver()
        self.assertEqual(len(self.notices()), 1)
        self.assertIn("市县范围", self.notices()[0]["message"])

    def test_identity_isolation_and_invalid_subscription_rejected(self):
        self.sub()
        self.assertEqual(
            self.other.get("/api/intelligence/subscriptions").json()["subscriptions"],
            [],
        )
        self.other.delete("/api/intelligence/subscriptions/s", headers=self.h)
        self.assertEqual(len(a.subscriptions(self.who)), 1)
        self.assertEqual(
            self.client.put(
                "/api/intelligence/subscriptions/x",
                headers=self.h,
                json={"province": "火星", "pests": ["条锈病"]},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.put(
                "/api/intelligence/subscriptions/x",
                json={"province": "河南", "pests": ["条锈病"]},
            ).status_code,
            403,
        )

    def test_guidelines_require_validity_region_and_strip_chemical_instructions(self):
        self.doc(
            kind="guideline",
            text="条锈病观察叶片黄色粉状物的排列。\n条锈病应喷药100克。",
        )
        self.assertEqual(a.search("条锈病")["results"], [])
        result = a.search("条锈病", "河南郑州")
        self.assertEqual(len(result["results"]), 1)
        self.assertNotIn("100克", json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["results"][0]["review_status"], "pending_review")
        self.assertEqual(a.search("条锈病", "山东济南")["results"], [])

    def test_source_html_parser_and_change_invalidates_prior_review(self):
        html = '<meta name="ArticleTitle" content="小麦条锈病技术指导"><meta name="PubDate" content="2026-11-01"><div class="TRS_Editor"><p>条锈病要观察叶片黄色粉状物。</p><script>ignore me</script></div>'
        url = "https://www.moa.gov.cn/xw/zwdt/202611/t20261101_1.htm"
        with patch.object(a, "fetch", return_value=(url, html, "v1")):
            d = a.ingest(url)
        a.approve(
            d["id"],
            "guideline",
            ["全国"],
            ["条锈病"],
            "2026-11-30",
            "fixture reviewer",
            "全国适用；只采用观察描述",
        )
        with patch.object(a, "fetch", return_value=(url, html, "v1")):
            self.assertEqual(a.ingest(url)["review_status"], "metadata_reviewed")
        with patch.object(a, "fetch", return_value=(url, html, "v2")):
            changed = a.ingest(url)
        self.assertEqual(changed["review_status"], "pending_metadata_review")
        self.assertEqual(changed["regions"], [])
        self.assertNotIn("ignore me", changed["text"])

    def test_ssrf_redirect_limits_and_invalid_metadata_fail_closed(self):
        for u in [
            "http://www.moa.gov.cn/xw/a",
            "https://www.moa.gov.cn.evil.test/xw/a",
            "https://127.0.0.1/xw/a",
            "https://www.moa.gov.cn:8000/xw/a",
            "https://user@www.moa.gov.cn/xw/a",
            "https://www.moa.gov.cn/xw/%2e%2e/a",
            "https://www.moa.gov.cn/xw/a?next=bad",
        ]:
            with self.subTest(url=u), self.assertRaises(ValueError):
                a.safe_url(u)

        class R:
            status_code = 302
            headers = {"Location": "https://127.0.0.1/private"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        with patch.object(
            a.requests, "get", return_value=R()
        ) as get, self.assertRaises(ValueError):
            a.fetch(a.INDEX)
        self.assertEqual(get.call_count, 1)
        with patch.object(
            a, "fetch", return_value=(a.INDEX, "<title>challenge</title>", "x")
        ), self.assertRaises(ValueError):
            a.ingest(a.INDEX)

    def test_refresh_failure_does_not_synthesize_risk(self):
        self.sub()
        with patch.object(a, "fetch", side_effect=OSError("private network detail")):
            state = a.refresh()
        self.assertEqual(state["state"], "unavailable")
        a.deliver()
        self.assertEqual(self.notices(), [])
        self.assertNotIn(
            "private", json.dumps(self.client.get("/api/intelligence/sources").json())
        )

    def test_bulletin_review_cannot_claim_unbounded_validity(self):
        self.doc()
        with self.assertRaises(ValueError):
            a.approve(
                "d", "bulletin", ["河南"], ["条锈病"], "2027-01-01", "fixture", "note"
            )
        self.assertEqual(a.documents()[0]["agronomic_review"], "pending_review")


if __name__ == "__main__":
    unittest.main()
