"""Twelve Data (forex/gold) aur Kraken (crypto) ke clients."""
from data.base import DataError, default_http_get, make_df

TD_URL = "https://api.twelvedata.com/time_series"
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


class TwelveDataClient:
    def __init__(self, api_key: str, http_get=default_http_get):
        self.api_key = api_key
        self.http_get = http_get

    def fetch(self, code: str, interval: str, outputsize: int):
        if not self.api_key:
            raise DataError("TWELVEDATA_API_KEY set nahi hai.")
        data = self.http_get(TD_URL, {
            "symbol": code, "interval": interval, "outputsize": outputsize,
            "order": "ASC", "timezone": "UTC", "apikey": self.api_key,
        })
        if not isinstance(data, dict) or data.get("status") == "error" or "values" not in data:
            msg = data.get("message") if isinstance(data, dict) else str(data)
            raise DataError(f"Twelve Data error: {msg}")
        from datetime import datetime, timezone

        rows = []
        for v in data["values"]:
            dt = datetime.strptime(v["datetime"][:19].replace("T", " "), "%Y-%m-%d %H:%M:%S" if len(v["datetime"]) > 10 else "%Y-%m-%d")
            ts = dt.replace(tzinfo=timezone.utc).timestamp()
            rows.append((ts, v["open"], v["high"], v["low"], v["close"], v.get("volume", 0)))
        return make_df(rows)


class KrakenClient:
    def __init__(self, http_get=default_http_get):
        self.http_get = http_get

    def fetch(self, code: str, interval_minutes: int, outputsize: int = 300):
        data = self.http_get(KRAKEN_URL, {"pair": code, "interval": interval_minutes})
        if not isinstance(data, dict) or data.get("error"):
            raise DataError(f"Kraken error: {data.get('error') if isinstance(data, dict) else data}")
        result = data.get("result", {})
        key = next((k for k in result if k != "last"), None)
        if key is None:
            raise DataError("Kraken ne candles nahi diye.")
        rows = [(r[0], r[1], r[2], r[3], r[4], r[6]) for r in result[key]]
        df = make_df(rows)
        return df.iloc[-outputsize:]
