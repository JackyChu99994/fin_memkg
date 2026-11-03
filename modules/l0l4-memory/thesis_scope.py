"""Conservative evidence-based scope checks before merging or invalidating theses.

Unknown scopes coexist. These guards do not establish that two statements are
factually contradictory; they prevent common, demonstrably different scopes
from being collapsed by a polarity-only state update.
"""
from __future__ import annotations

import json
import re

CORRECTION = re.compile(r"更正|修正|撤回|撤销|取消|终止|暂停|未通过|否认|不实|转给|退单|解约|恢复|cancel|terminat|withdraw|reinstat|not approved", re.I)


def infer_scope(event, news=""):
    focus = str(event.get("target", "")) + " " + str(event.get("reason", ""))
    metrics = set()
    if re.search(r"归母|归属于.*股东", focus):
        metrics.add("attributable_profit")
    elif re.search(r"净利润|净利", focus):
        metrics.add("net_profit")
    if re.search(r"营业收入|营收", focus):
        metrics.add("revenue")
    if re.search(r"市占率|市场份额", focus):
        metrics.add("market_share")
    if "装车量" in focus:
        metrics.add("installation_volume")
    # Use the complete source to identify business families only when needed.
    text = focus + " " + news
    if metrics:
        family = "financial"
    elif re.search(r"投资|出资|认缴|基金|investment|invest", text, re.I):
        family = "investment"
    elif re.search(r"订单|合同|供货|签约|合作协议|contract|order", text, re.I):
        family = "commercial_agreement"
    elif re.search(r"回购|注销|repurchase|buyback", text, re.I):
        family = "repurchase"
    elif re.search(r"建设|项目|扩产|project|construction", text, re.I):
        family = "project"
    else:
        family = "unknown"
    bases = {kind for word, kind in (("同比", "YoY"), ("环比", "QoQ")) if word in focus}
    periods = set(re.findall(r"前三季度|前三季|上半年|下半年|第一季度|第二季度|第三季度|第四季度|一季度|二季度|三季度|四季度|全年", focus))
    years = set(re.findall(r"(20\d{2})年", focus))
    if not years:
        source_years = set(re.findall(r"(20\d{2})年", news))
        years = source_years if len(source_years) == 1 else set()
    aliases = {"前三季": "前三季度", "一季度": "第一季度", "二季度": "第二季度", "三季度": "第三季度", "四季度": "第四季度"}
    periods = {aliases.get(period, period) for period in periods}
    region = "domestic" if "国内" in focus else "overseas" if "海外" in focus else None
    phase = "proposal" if re.search(r"提议|propos", text, re.I) else "planned" if re.search(r"拟|预计|计划|预告|预增|expect|plan", text, re.I) else "reported"
    return {"family": family, "metric": next(iter(metrics)) if len(metrics) == 1 else None,
        "basis": next(iter(bases)) if len(bases) == 1 else None,
        "period": next(iter(periods)) if len(periods) == 1 else None,
        "year": next(iter(years)) if len(years) == 1 else None, "region": region,
        "phase": phase, "ambiguous": len(metrics) > 1 or len(bases) > 1 or len(periods) > 1 or len(years) > 1}


def stored_scope(edge):
    value = edge.get("props", {}).get("thesis_scope")
    if value:
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError):
            pass
    return infer_scope({"target": edge.get("target_name", ""), "reason": edge.get("props", {}).get("reason", "")})


def matching_scope(old, event):
    left, right = stored_scope(old), json.loads(event["thesis_scope"])
    if left.get("ambiguous") or right.get("ambiguous") or left["family"] != right["family"]:
        return False
    if left["family"] == "financial":
        required = ("metric", "basis", "period", "year")
        return all(left.get(key) and right.get(key) and left[key] == right[key] for key in required) and left.get("region") == right.get("region")
    return left["family"] != "unknown" and old.get("target_name") == event["target"]


def can_invalidate(old, event, news, *, explicitly_requested=False):
    if old.get("props", {}).get("date", "")[:10] > event.get("date", "")[:10]:
        return False
    if old.get("source_name") != event["source"] or not matching_scope(old, event):
        return False
    if stored_scope(old)["family"] == "financial":
        return explicitly_requested or bool(CORRECTION.search(news))
    return bool(CORRECTION.search(news))


def can_reinforce(old, event):
    if old.get("props", {}).get("date", "")[:10] > event.get("date", "")[:10]:
        return False
    if not matching_scope(old, event):
        return False
    return stored_scope(old).get("phase") == json.loads(event["thesis_scope"]).get("phase")
