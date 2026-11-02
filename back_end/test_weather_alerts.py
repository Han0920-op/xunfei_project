"""Dated official warning lifecycle and isolated demo, with synthetic source data."""

import copy, json, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
import personal, agri_sources, weather_alerts as w, regional_context
from main import app


class WeatherAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = patch.object(personal, "PATH", Path(self.tmp.name) / "db")
        self.path.start()
        self.now = datetime(2026, 11, 2, 12, tzinfo=personal.TZ)
        self.clock = patch.object(personal, "now", return_value=self.now)
        self.clock.start()
        self.a = TestClient(app)
        self.b = TestClient(app)
        self.h = {"X-Zhimai-Personal": "1"}
        for c in (self.a, self.b):
            c.get("/api/personal/session")
        self.who = self.a.cookies.get("zhimai_owner")

    def tearDown(self):
        self.clock.stop()
        self.path.stop()
        self.tmp.cleanup()

    def sub(self, id="zz", **changes):
        body = {
            "province": "河南",
            "city": "郑州",
            "pests": [],
            "weather_enabled": True,
            "weather_types": ["暴雨", "大风", "寒潮", "霜冻"],
            "max_daily": 3,
            "quiet_start": "22:00",
            "quiet_end": "07:00",
        } | changes
        r = self.a.put(
            "/api/intelligence/subscriptions/" + id, headers=self.h, json=body
        )
        self.assertEqual(r.status_code, 200, r.text)
        return body

    def record(self, **changes):
        return {
            "id": "source-warning",
            "headline": "测试替身：郑州市暴雨橙色预警",
            "senderName": "测试替身气象台",
            "pubTime": self.now.isoformat(),
            "startTime": self.now.isoformat(),
            "endTime": (self.now + timedelta(hours=3)).isoformat(),
            "typeName": "暴雨",
            "level": "橙色",
            "areaCodes": ["410100"],
            "status": "active",
            "text": "测试记录，不是真实灾害。",
            "url": w.PORTAL_URL,
        } | changes

    def refresh(self, records):
        with patch.object(w, "fetch_records", return_value=records):
            return w.refresh()

    def notes(self):
        return personal.listing(self.who, "notifications")

    def test_demo_is_explicit_ephemeral_owned_and_does_not_need_model_or_source(self):
        self.sub()
        for hazard in ("暴雨", "大风", "寒潮", "霜冻"):
            for action in ("发布", "升级", "解除"):
                with patch.object(
                    w, "fetch_records", side_effect=AssertionError("no network")
                ):
                    r = self.a.post(
                        "/api/weather-alerts/demo",
                        headers=self.h,
                        json={
                            "subscription_id": "zz",
                            "hazard": hazard,
                            "level": "橙色",
                            "action": action,
                        },
                    )
                self.assertEqual(r.status_code, 200)
                d = r.json()
                self.assertTrue(d["is_demo"])
                self.assertFalse(d["persisted"])
                self.assertIn("不代表", d["message"])
                self.assertIn("演示", d["source"])
                self.assertEqual(len(d["advice"]), 3)
        self.assertEqual(self.notes(), [])
        with personal.db() as c:
            w.ensure(c)
            self.assertEqual(
                c.execute("SELECT count(*) FROM weather_warning_events").fetchone()[0],
                0,
            )
        self.assertEqual(
            self.b.post(
                "/api/weather-alerts/demo",
                headers=self.h,
                json={"subscription_id": "zz"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.a.post("/api/weather-alerts/demo", json={}).status_code, 403
        )

    def test_opt_in_required_scope_matching_and_exact_repeat_dedup(self):
        self.sub(weather_enabled=False, pests=["条锈病"])
        self.refresh([self.record()])
        w.deliver()
        self.assertEqual(self.notes(), [])
        self.sub()
        w.deliver()
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.assertFalse(self.notes()[0]["is_demo"])
        self.refresh([self.record()])
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.sub("second")
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.assertEqual(
            self.b.get("/api/weather-alerts/status").json()["warnings"], []
        )

    def test_wrong_county_city_province_hazard_level_future_expired_do_not_notify(self):
        self.sub(weather_min_level="黄色")
        records = [
            self.record(id="wrong-province", areaCodes=["370100"]),
            self.record(id="wrong-city", areaCodes=["410900"]),
            self.record(id="wrong-hazard", typeName="高温"),
            self.record(id="low", level="蓝色"),
            self.record(
                id="future",
                pubTime=(self.now + timedelta(hours=1)).isoformat(),
                startTime=(self.now + timedelta(hours=1)).isoformat(),
            ),
            self.record(
                id="expired",
                pubTime=(self.now - timedelta(hours=2)).isoformat(),
                startTime=(self.now - timedelta(hours=2)).isoformat(),
                endTime=(self.now - timedelta(hours=1)).isoformat(),
            ),
        ]
        self.refresh(records)
        w.deliver()
        self.assertEqual(self.notes(), [])

    def test_parent_scope_county_and_municipality_rules(self):
        self.sub()
        self.refresh([self.record(areaCodes=["410102"])])
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.sub("bj", province="北京", city="北京")
        self.refresh([self.record(id="bj", areaCodes=["110101"])])
        w.deliver()
        self.assertEqual(len(self.notes()), 2)
        self.sub("province", city="")
        self.refresh([self.record(id="whole-henan", areaCodes=["410900"])])
        w.deliver()
        self.assertEqual(len(self.notes()), 3)

    def test_quiet_frequency_and_explicit_urgent_upgrade_consent(self):
        self.sub(max_daily=1, quiet_start="11:00", quiet_end="13:00")
        self.refresh([self.record(level="黄色")])
        w.deliver()
        self.assertEqual(self.notes(), [])
        self.sub(max_daily=1, quiet_start="12:00", quiet_end="12:00")
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.refresh(
            [
                self.record(
                    level="红色", pubTime=(self.now + timedelta(minutes=1)).isoformat()
                )
            ]
        )
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.sub(
            max_daily=1, weather_urgent=True, quiet_start="11:00", quiet_end="13:00"
        )
        w.deliver()
        self.assertEqual(len(self.notes()), 2)
        self.assertIn("升级", self.notes()[0]["name"])
        self.assertTrue(self.notes()[0]["urgent"])
        self.refresh(
            [
                self.record(
                    level="红色",
                    headline="同级内容更新",
                    pubTime=(self.now + timedelta(minutes=2)).isoformat(),
                )
            ]
        )
        w.deliver()
        self.assertEqual(len(self.notes()), 2)

    def test_source_failure_stale_schema_and_empty_feed_never_invent_clearance(self):
        self.sub()
        self.refresh([self.record()])
        w.deliver()
        self.refresh([])
        self.assertEqual(len(w.active_for(self.who)["warnings"]), 1)
        self.assertEqual(len(self.notes()), 1)
        with patch.object(
            w, "fetch_records", side_effect=OSError("secret source text")
        ):
            meta = w.refresh()
        self.assertEqual(meta["state"], "unavailable")
        self.assertEqual(w.active_for(self.who)["warnings"], [])
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.assertNotIn("secret", json.dumps(meta))
        self.refresh([["undocumented", "array"]])
        self.assertEqual(
            w.active_for(self.who)["source"]["state"], "unsupported_source_schema"
        )
        self.refresh([self.record()])
        with patch.object(
            personal, "now", return_value=self.now + timedelta(minutes=25)
        ):
            self.assertEqual(w.active_for(self.who)["source"]["state"], "stale")

    def test_cancel_requires_explicit_source_and_only_informs_previous_recipients(self):
        self.sub()
        self.refresh([self.record()])
        w.deliver()
        self.refresh(
            [
                self.record(
                    id="cancel",
                    status="Cancel",
                    references=["source-warning"],
                    pubTime=(self.now + timedelta(minutes=1)).isoformat(),
                )
            ]
        )
        w.deliver()
        self.assertEqual(len(self.notes()), 2)
        self.assertIn("解除", self.notes()[0]["name"])
        self.assertEqual(w.active_for(self.who)["warnings"], [])
        self.sub("new", province="山东", city="济南")
        w.deliver()
        self.assertEqual(len(self.notes()), 2)

    def test_referenced_updates_supersede_original_without_duplicate_live_warning(self):
        self.sub()
        original = self.record(level="黄色")
        update = self.record(
            id="updated",
            msgType="Update",
            references=["source-warning"],
            level="红色",
            pubTime=(self.now + timedelta(minutes=1)).isoformat(),
        )
        self.refresh([original, update])
        w.deliver()
        self.assertEqual(len(self.notes()), 1)
        self.assertEqual(len(w.active_for(self.who)["warnings"]), 1)
        self.assertEqual(w.active_for(self.who)["warnings"][0]["level"], "红色")
        self.refresh([original])
        self.assertEqual(len(w.active_for(self.who)["warnings"]), 1)
        self.assertEqual(w.active_for(self.who)["warnings"][0]["level"], "红色")

    def test_explicit_cap_cancellation_without_info_uses_only_known_reference_scope(
        self,
    ):
        self.sub()
        self.refresh([self.record()])
        w.deliver()
        cancel = {
            "identifier": "cap-cancel",
            "sender": "fixture-cma",
            "sent": (self.now + timedelta(minutes=1)).isoformat(),
            "msgType": "Cancel",
            "references": ["source-warning"],
        }
        self.refresh([cancel])
        w.deliver()
        self.assertIn("解除", self.notes()[0]["name"])
        self.assertTrue(self.notes()[1]["superseded"])
        self.assertEqual(w.active_for(self.who)["warnings"], [])
        cancel["references"] = ["unknown"]
        meta = self.refresh([cancel])
        self.assertEqual(meta["rejected"], 1)

    def test_unsubscribe_pause_and_cross_province_code_rejected(self):
        self.sub()
        self.refresh([self.record()])
        self.sub(enabled=False)
        w.deliver()
        self.assertEqual(self.notes(), [])
        self.sub()
        self.a.delete("/api/intelligence/subscriptions/zz", headers=self.h)
        w.deliver()
        self.assertEqual(self.notes(), [])
        r = self.a.put(
            "/api/intelligence/subscriptions/bad",
            headers=self.h,
            json={
                "province": "河南",
                "city": "济南",
                "weather_enabled": True,
                "pests": [],
            },
        )
        self.assertEqual(r.status_code, 400)
        r = self.a.put(
            "/api/intelligence/subscriptions/bad",
            headers=self.h,
            json={
                "province": "河南",
                "city": "未知市",
                "weather_enabled": True,
                "pests": [],
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_standard_cap_actual_public_only_entities_and_incomplete_records_fail_closed(
        self,
    ):
        cap = b"""<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>cap-1</identifier><sender>test</sender><sent>2026-11-02T12:00:00+08:00</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info><language>zh-CN</language><event>\xe6\x9a\xb4\xe9\x9b\xa8</event><headline>\xe6\x9a\xb4\xe9\x9b\xa8\xe6\xa9\x99\xe8\x89\xb2\xe9\xa2\x84\xe8\xad\xa6</headline><senderName>fixture</senderName><expires>2026-11-02T15:00:00+08:00</expires><area><geocode><valueName>GB/T 2260</valueName><value>410100</value></geocode></area></info></alert>"""
        parsed = w.cap_records(cap)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(w.normalize(parsed[0])["area_codes"], ["410100"])
        self.assertEqual(w.cap_records(cap.replace(b"Actual", b"Exercise")), [])
        with self.assertRaises(ValueError):
            w.cap_records(
                b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><alert/>'
            )
        for changes in (
            {"areaCodes": []},
            {"endTime": ""},
            {"level": "未知"},
            {"senderName": ""},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                w.normalize(self.record(**changes))

    def test_stale_referenced_update_cannot_reopen_later_cancelled_warning(self):
        self.sub()
        self.refresh([self.record()])
        w.deliver()
        cancel = self.record(
            id="cancel-final",
            msgType="Cancel",
            references=["source-warning"],
            pubTime=(self.now + timedelta(minutes=2)).isoformat(),
        )
        self.refresh([cancel])
        w.deliver()
        old_update = self.record(
            id="late-old-update",
            msgType="Update",
            references=["source-warning"],
            pubTime=(self.now + timedelta(minutes=1)).isoformat(),
        )
        self.refresh([old_update])
        self.assertEqual(w.active_for(self.who)["warnings"], [])
        with self.assertRaises(ValueError):
            w.cap_records(b"<html><title>challenge</title></html>")

    def test_source_fetch_has_fixed_host_no_redirect_and_bounded_schema(self):
        r = Mock(status_code=302)
        r.__enter__ = Mock(return_value=r)
        r.__exit__ = Mock(return_value=False)
        with patch.object(w.requests, "get", return_value=r) as get, self.assertRaises(
            ValueError
        ):
            w.fetch_records()
        self.assertEqual(get.call_args.args[0], w.SOURCE_URL)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        d = self.record(url="https://attacker.test/")
        self.assertEqual(w.normalize(d)["source_url"], w.PORTAL_URL)

    def test_chat_receives_only_real_warnings_and_no_demo_fact(self):
        self.sub()
        self.refresh([self.record()])
        data = regional_context.prompt_context(regional_context.context(self.who, "zz"))
        self.assertEqual(len(data["weather_warnings"]), 1)
        self.assertFalse("演示" in data["weather_warnings"][0]["title"])
        self.assertIn("气象灾害预警", data["limitations"])
        self.a.post(
            "/api/weather-alerts/demo", headers=self.h, json={"subscription_id": "zz"}
        )
        self.assertEqual(
            len(
                regional_context.prompt_context(
                    regional_context.context(self.who, "zz")
                )["weather_warnings"]
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
