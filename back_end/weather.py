"""Real-only AMap forecasts for the conversational farmer agent.

An unavailable forecast never becomes simulated weather. City forecasts provide
context, not field measurements, rainfall amounts, or permission to spray.
"""
import json
import re
from datetime import date as Date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import config

CHINA_TIME = ZoneInfo("Asia/Shanghai")
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
MAX_FORECAST_AGE = timedelta(hours=24)
_CITY_CODES = {
    "郑州": "410100", "济南": "370100", "石家庄": "130100",
    "南京": "320100", "合肥": "340100", "西安": "610100",
    "武汉": "420100", "北京": "110000", "天津": "120000",
    "上海": "310000", "重庆": "500000", "成都": "510100",
    "太原": "140100", "兰州": "620100",
}
_PROVINCES = {
    "河南", "山东", "河北", "江苏", "安徽", "陕西", "湖北", "四川",
    "山西", "甘肃", "浙江", "福建", "江西", "湖南", "广东", "海南",
    "辽宁", "吉林", "黑龙江", "贵州", "云南", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
}
_MUNICIPALITIES = {"110000", "120000", "310000", "500000"}
_PROVINCE_PREFIXES = {
    "11", "12", "13", "14", "15", "21", "22", "23", "31", "32", "33",
    "34", "35", "36", "37", "41", "42", "43", "44", "45", "46", "50",
    "51", "52", "53", "54", "61", "62", "63", "64", "65", "71", "81", "82",
}


def _now():
    return datetime.now(CHINA_TIME)


def _location_code(location):
    if not isinstance(location, str) or len(location) > 80:
        return None
    location = location.strip()
    if location in _CITY_CODES:
        return _CITY_CODES[location]
    if location.endswith("市") and location[:-1] in _CITY_CODES:
        return _CITY_CODES[location[:-1]]
    if re.fullmatch(r"[0-9]{6}", location) and location[:2] in _PROVINCE_PREFIXES:
        # An explicit county/city adcode is accepted, subject to provider match.
        if location.endswith("0000") and location not in _MUNICIPALITIES:
            return None
        return location
    return None


def _requested_day(value, today):
    if value in ("today", "今天"):
        return today
    if value in ("tomorrow", "明天"):
        return today + timedelta(days=1)
    if not isinstance(value, str):
        return None
    try:
        parsed = Date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if today <= parsed <= today + timedelta(days=3) else None


def _text(value, max_length=100):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError("missing or invalid provider field")
    return re.sub(r"[\x00-\x1f]", "", value).strip()


def _forecast_row(cast):
    if not isinstance(cast, dict):
        raise ValueError("invalid forecast row")
    day = Date.fromisoformat(_text(cast.get("date"), 10)).isoformat()
    low = _text(cast.get("nighttemp"), 12)
    high = _text(cast.get("daytemp"), 12)
    if not all(re.fullmatch(r"-?\d{1,2}(?:\.\d+)?", x) for x in (low, high)):
        raise ValueError("invalid temperature")
    return {
        "date": day,
        "day_weather": _text(cast.get("dayweather")),
        "night_weather": _text(cast.get("nightweather")),
        "low_celsius": low,
        "high_celsius": high,
        "day_wind_direction": _text(cast.get("daywind")),
        "night_wind_direction": _text(cast.get("nightwind")),
        "day_wind_force": _text(cast.get("daypower"), 30),
        "night_wind_force": _text(cast.get("nightpower"), 30),
    }


def get_weather(location: str, date: str = "today") -> str:
    """Return a dated provider forecast or an explicit failure as JSON text."""
    now = _now()
    result = {
        "status": "unavailable", "provider": "高德天气预报", "source": None,
        "simulated": False, "requested_location": location if isinstance(location, str) else "",
        "requested_date": date if isinstance(date, str) else "",
        "retrieved_at": now.isoformat(), "report_time": None, "forecast": [],
        "can_assess_spraying": False,
        "limitations": "这是城市或区县级天气预报，不是田间实测；接口不提供降水量、降雨概率、阵风、叶面湿度，不能单凭此结果认定病害或判断可以施药。",
    }

    def finish(status, code, message):
        result.update(status=status, error_code=code, message=message)
        return json.dumps(result, ensure_ascii=False)

    code = _location_code(location)
    if code is None:
        normalized = location.strip().removesuffix("省") if isinstance(location, str) else ""
        message = (
            "仅有省名不足以查询田间相关天气，请补充地块所在市县或准确的六位行政区编码。"
            if normalized in _PROVINCES or re.fullmatch(r"\d{2}0000", normalized or "")
            else "请提供地块所在市县。当前支持郑州、济南、石家庄、南京、合肥、西安、武汉、北京、天津、上海、重庆、成都、太原、兰州，或用户确认的六位市县行政区编码；不能猜测未收录或重名地点。"
        )
        return finish("needs_location", "location_not_resolved", message)
    day = _requested_day(date, now.date())
    if day is None:
        return finish("unavailable", "unsupported_date", "当前仅支持今天、明天或未来三天内的YYYY-MM-DD日期，不查询历史天气。")
    result["forecast_date"] = day.isoformat()
    result["requested_adcode"] = code
    if not config.WEATHER_API_KEY:
        return finish("unavailable", "weather_not_configured", "尚未配置真实天气服务，当前没有取得天气数据；不能使用模拟天气进行判断。")
    try:
        response = requests.get(
            WEATHER_URL,
            params={"city": code, "key": config.WEATHER_API_KEY, "extensions": "all"},
            timeout=(3.05, 10),
        )
        if response.status_code != 200:
            return finish("unavailable", "provider_http_error", "天气服务暂不可用，请稍后重试或核对当地最新天气预报。")
        response.encoding = "utf-8"
        try:
            data = response.json()
        except ValueError:
            return finish("unavailable", "invalid_provider_data", "天气服务返回的数据不是有效JSON，暂不作为判断依据。")
        if not isinstance(data, dict) or data.get("status") != "1":
            return finish("unavailable", "provider_rejected", "天气服务未成功返回预报，请检查服务配置或稍后重试。")
        forecasts = data.get("forecasts")
        if not isinstance(forecasts, list) or len(forecasts) != 1 or not isinstance(forecasts[0], dict):
            raise ValueError("invalid or ambiguous city forecast")
        forecast = forecasts[0]
        if forecast.get("adcode") != code:
            return finish("needs_location", "provider_location_mismatch", "天气服务返回的地点与请求不一致，请重新确认地块所在市县或行政区编码。")
        report_string = _text(forecast.get("reporttime"), 40)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?", report_string):
            raise ValueError("report time must contain date and clock time")
        issued = datetime.fromisoformat(report_string)
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=CHINA_TIME)
        issued = issued.astimezone(CHINA_TIME)
        age = now - issued
        if age < -timedelta(minutes=10) or age > MAX_FORECAST_AGE:
            return finish("unavailable", "stale_or_future_forecast", "天气预报发布时间异常或超过24小时，暂不作为当前天气依据。")
        casts = forecast.get("casts")
        if not isinstance(casts, list) or not 1 <= len(casts) <= 7:
            raise ValueError("missing forecasts")
        rows = [_forecast_row(cast) for cast in casts]
        if len({row["date"] for row in rows}) != len(rows):
            raise ValueError("duplicate forecast dates")
        selected = [row for row in rows if row["date"] == day.isoformat()]
        if not selected:
            return finish("unavailable", "date_not_covered", "天气服务返回的数据不覆盖所请求日期，不能用其他日期的天气代替。")
        city = _text(forecast.get("city"), 80)
        row = selected[0]
        result.update(
            status="ok", source="高德天气预报（真实接口）", location=city,
            adcode=code, report_time=issued.isoformat(), forecast=selected,
            available_dates=sorted(row["date"] for row in rows),
            weather=f"白天{row['day_weather']} / 夜间{row['night_weather']}",
            temperature=f"{row['low_celsius']}~{row['high_celsius']}℃",
            wind=f"白天{row['day_wind_direction']} {row['day_wind_force']}级 / 夜间{row['night_wind_direction']} {row['night_wind_force']}级",
            message="已取得指定地点和日期的城市／区县天气预报。",
        )
        return json.dumps(result, ensure_ascii=False)
    except requests.Timeout:
        return finish("unavailable", "provider_timeout", "天气查询超时，没有取得可靠天气，请稍后重试。")
    except requests.RequestException:
        # Do not leak request URLs or exception strings containing the API key.
        return finish("unavailable", "provider_network_error", "暂时无法连接天气服务，没有取得可靠天气。")
    except (ValueError, KeyError, TypeError, OverflowError):
        return finish("unavailable", "invalid_provider_data", "天气服务返回的数据不完整或无法校验，暂不作为判断依据。")
