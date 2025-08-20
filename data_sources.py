# -*- coding: utf-8 -*-
from typing import Optional, Tuple, Dict, Any, List
import re
import requests
import pandas as pd
from pycoingecko import CoinGeckoAPI
from .config import DEFAULT_VS_CURRENCY, DEFAULT_DAYS, DEFAULT_INTERVAL

cg = CoinGeckoAPI()
DEX_BASE = "https://api.dexscreener.com"
DEX_ENDPOINT_SEARCH = f"{DEX_BASE}/latest/dex/search"
DEX_ENDPOINT_PAIRS = f"{DEX_BASE}/latest/dex/pairs"
DEX_ENDPOINT_TOKEN_PAIRS = f"{DEX_BASE}/token-pairs/v1"
HTTP_TIMEOUT = 20

def parse_chain_and_address(query: str) -> Optional[Tuple[str, str]]:
    q = query.strip()
    m = re.match(r"^([a-z0-9\-]+):([A-Za-z0-9x]+)$", q)
    if m:
        return m.group(1), m.group(2)
    url_m = re.match(r"^https?://dexscreener\.com/([^/]+)/([^/?#]+)", q)
    if url_m:
        return url_m.group(1), url_m.group(2)
    return None

def dexs_search_pairs(query: str) -> List[Dict[str, Any]]:
    r = requests.get(DEX_ENDPOINT_SEARCH, params={"q": query}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("pairs", []) if isinstance(data, dict) else []

def dexs_get_pair(chain: str, pair_id: str) -> Optional[Dict[str, Any]]:
    url = f"{DEX_ENDPOINT_PAIRS}/{chain}/{pair_id}"
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        return None
    d = r.json()
    if isinstance(d, dict) and d.get("pairs"):
        return d["pairs"][0]
    return None

def dexs_get_pools_for_token(chain: str, token_address: str) -> List[Dict[str, Any]]:
    url = f"{DEX_ENDPOINT_TOKEN_PAIRS}/{chain}/{token_address}"
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json() if isinstance(r.json(), list) else []

def cg_find_id_by_symbol_or_name(q: str) -> Optional[str]:
    try:
        res = cg.search(q)
        for c in res.get("coins", []):
            if c.get("symbol", "").lower() == q.lower():
                return c.get("id")
        for c in res.get("coins", []):
            if c.get("name", "").lower() == q.lower():
                return c.get("id")
        if res.get("coins"):
            return res["coins"][0]["id"]
    except Exception:
        return None
    return None

def cg_market_chart_df(coin_id: str, days: int = DEFAULT_DAYS,
                       vs: str = DEFAULT_VS_CURRENCY,
                       interval: str = DEFAULT_INTERVAL) -> Optional[pd.DataFrame]:
    try:
        data = cg.get_coin_market_chart_by_id(id=coin_id, vs_currency=vs, days=days, interval=interval)
        prices = data.get("prices", [])
        vols = data.get("total_volumes", [])
        if not prices:
            return None
        df_p = pd.DataFrame(prices, columns=["time", "price"])
        df_p["time"] = pd.to_datetime(df_p["time"], unit="ms")
        df_p.set_index("time", inplace=True)
        df_v = pd.DataFrame(vols, columns=["time", "volume"]) if vols else None
        if df_v is not None:
            df_v["time"] = pd.to_datetime(df_v["time"], unit="ms")
            df_v.set_index("time", inplace=True)
            df = df_p.join(df_v, how="left")
        else:
            df = df_p
            df["volume"] = float("nan")
        ohlc = df["price"].resample("1D").ohlc()
        vol = df["volume"].resample("1D").sum(min_count=1)
        out = ohlc.join(vol)
        out.dropna(how="any", inplace=True)
        out.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}, inplace=True)
        return out
    except Exception:
        return None

def map_dex_to_cg_id_from_pair(pair: Dict[str, Any]) -> Optional[str]:
    if not pair:
        return None
    base = pair.get("baseToken", {})
    for s in [base.get("symbol", ""), base.get("name", "")]:
        if s:
            cid = cg_find_id_by_symbol_or_name(s)
            if cid:
                return cid
    return None
