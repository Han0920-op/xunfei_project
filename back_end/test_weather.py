"""Real-weather adapter tests: no external network or credentials."""
import copy
import json
from datetime import datetime
from unittest import TestCase, main
from unittest.mock import Mock, patch

import requests

import weather

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=weather.CHINA_TIME)


def payload():
    def day(date, temp, wx):
        return {"date": date, "dayweather": wx, "nightweather": "多云",
                "daytemp": str(temp), "nighttemp": "10", "daywind": "东北",
                "nightwind": "北", "daypower": "≤3", "nightpower": "3"}
    return {"status": "1", "forecasts": [{
        "city": "郑州市", "adcode": "410100", "reporttime": "2026-10-28 11:00:00",
        "casts": [day("2026-10-28", 20, "晴"), day("2026-10-29", 16, "小雨")],
    }]}


class WeatherTests(TestCase):
    def setUp(self):
        self.clock = patch("weather._now", return_value=NOW)
        self.clock.start()
        self.key = patch("config.WEATHER_API_KEY", "test-secret-weather-key")
        self.key.start()
        self.provider = patch("weather.requests.get")
        self.get = self.provider.start()
        self.data = payload()
        self.get.return_value = Mock(status_code=200)
        self.get.return_value.json.side_effect = lambda: copy.deepcopy(self.data)

    def tearDown(self):
        self.provider.stop()
        self.key.stop()
        self.clock.stop()

    def query(self, location="郑州", date="today"):
        return json.loads(weather.get_weather(location, date))

    def test_today_is_a_real_dated_forecast_with_limitations(self):
        r = self.query()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["forecast"][0]["date"], "2026-10-28")
        self.assertEqual(r["report_time"], "2026-10-28T11:00:00+08:00")
        self.assertFalse(r["simulated"])
        self.assertFalse(r["can_assess_spraying"])
        self.assertIn("不是田间实测", r["limitations"])
        self.assertNotIn("无明显降水", json.dumps(r, ensure_ascii=False))
        self.get.assert_called_once()
        self.assertEqual(self.get.call_args.kwargs["params"]["city"], "410100")

    def test_tomorrow_selects_tomorrow_not_first_cast(self):
        r = self.query(date="tomorrow")
        self.assertEqual(r["forecast_date"], "2026-10-29")
        self.assertEqual(len(r["forecast"]), 1)
        self.assertIn("小雨", r["weather"])
        self.assertIn("16", r["temperature"])

    def test_explicit_iso_date_is_respected(self):
        self.assertEqual(self.query(date="2026-10-29")["forecast"][0]["date"], "2026-10-29")

    def test_missing_key_never_returns_fabricated_weather(self):
        with patch("config.WEATHER_API_KEY", ""):
            r = self.query()
        self.assertEqual(r["status"], "unavailable")
        self.assertEqual(r["error_code"], "weather_not_configured")
        self.assertEqual(r["forecast"], [])
        self.assertIsNone(r["source"])
        self.get.assert_not_called()

    def test_province_unknown_ambiguous_and_empty_locations_need_confirmation(self):
        for location in ["", "河南", "河南省", "410000", "朝阳", "不知道", "0", None, "999999"]:
            r = self.query(location)
            self.assertEqual(r["status"], "needs_location", location)
            self.assertEqual(r["forecast"], [])
        self.get.assert_not_called()

    def test_city_suffix_and_confirmed_county_adcode_are_supported(self):
        self.assertEqual(self.query("郑州市")["status"], "ok")
        self.data["forecasts"][0].update(adcode="410102", city="中原区")
        self.assertEqual(self.query("410102")["location"], "中原区")

    def test_provider_location_mismatch_cannot_silently_choose_other_city(self):
        self.data["forecasts"][0]["adcode"] = "410200"
        r = self.query()
        self.assertEqual(r["status"], "needs_location")
        self.assertEqual(r["error_code"], "provider_location_mismatch")

    def test_bad_dates_do_not_call_provider(self):
        for day in ["yesterday", "2026-10-27", "2026-11-05", "no-date", 123]:
            self.assertEqual(self.query(date=day)["error_code"], "unsupported_date")
        self.get.assert_not_called()

    def test_uncovered_date_does_not_use_a_different_forecast(self):
        r = self.query(date="2026-10-30")
        self.assertEqual(r["status"], "unavailable")
        self.assertEqual(r["error_code"], "date_not_covered")
        self.assertEqual(r["forecast"], [])

    def test_stale_and_future_report_times_are_not_used(self):
        for issued in ["2026-10-26 11:00:00", "2026-10-29 11:00:00"]:
            self.data["forecasts"][0]["reporttime"] = issued
            self.assertEqual(self.query()["error_code"], "stale_or_future_forecast")

    def test_malformed_data_is_unavailable(self):
        for update in [
            {"casts": []}, {"reporttime": "2026-10-28"}, {"casts": [None]},
            {"casts": [{**payload()["forecasts"][0]["casts"][0], "daytemp": "未知"}]},
            {"casts": [payload()["forecasts"][0]["casts"][0]] * 2},
        ]:
            self.data = payload()
            self.data["forecasts"][0].update(update)
            self.assertEqual(self.query()["status"], "unavailable")

    def test_provider_failure_does_not_leak_secret(self):
        for failure, code in [
            (requests.Timeout("test-secret-weather-key"), "provider_timeout"),
            (requests.ConnectionError("url?key=test-secret-weather-key"), "provider_network_error"),
        ]:
            self.get.side_effect = failure
            r = self.query()
            self.assertEqual(r["error_code"], code)
            self.assertNotIn("test-secret-weather-key", json.dumps(r))
            self.assertEqual(r["forecast"], [])

    def test_provider_auth_http_and_invalid_json_fail_closed(self):
        self.data["status"] = "0"
        self.data["info"] = "INVALID_USER_KEY test-secret-weather-key"
        self.assertEqual(self.query()["error_code"], "provider_rejected")
        self.get.return_value.status_code = 503
        self.assertEqual(self.query()["error_code"], "provider_http_error")
        self.get.return_value.status_code = 200
        self.get.return_value.json.side_effect = ValueError("bad JSON")
        r = self.query()
        self.assertEqual(r["error_code"], "invalid_provider_data")
        self.assertNotIn("test-secret-weather-key", json.dumps(r))


if __name__ == "__main__":
    main(verbosity=2)
