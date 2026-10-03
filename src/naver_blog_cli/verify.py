# 작성: 송중호 (2026-10-03) — 신규 파일. 원고의 장소·사실을 네이버 검색으로 확인한다.
"""원고 사실 확인.

1. 로컬 LLM 이 원고에서 장소 이름과 확인할 사실 문장을 뽑는다 (JSON).
2. 장소: 네이버 지역 검색 → 웹문서·블로그 순으로 실제로 있는지 본다 (search.find_place).
   이 판정은 LLM 을 거치지 않는다. 지어낸 장소를 잡는 데 가장 확실한 신호다.
3. 사실: 뉴스·웹문서를 검색해 결과 요약을 LLM 에게 보여주고 맞는지 판단하게 한다.
   같은 모델이 판단하므로 참고용이다. 그래서 원고를 자동으로 고치지 않고 보고서만 만든다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import llm, search

EXTRACT_SYSTEM = """너는 블로그 원고에서 사실 확인이 필요한 항목을 뽑는 도우미다.
JSON 으로만 답한다. 형식:
{"region": "글의 주 지역(예: 세종시, 없으면 빈 문자열)",
 "places": ["원고에 나온 구체적인 장소·시설·공원·다리 이름", ...],
 "facts": [{"claim": "확인할 사실 문장(원고 표현 그대로 짧게)", "query": "네이버 검색어"}, ...]}
규칙:
- places 는 고유 이름만 (예: '국립세종수목원'). '카페', '공원' 같은 일반 명사는 빼고, 최대 12개.
- facts 는 날짜·기간·운영 여부·수치·행사처럼 틀리면 곤란한 것만, 최대 8개.
- 감상, 일반적인 팁은 넣지 않는다."""

JUDGE_SYSTEM = """너는 사실 확인 도우미다. '주장'이 '검색 결과'로 뒷받침되는지 판단한다.
JSON 으로만 답한다: {"verdict": "supported|contradicted|unknown", "reason": "한 문장 근거"}
- supported: 검색 결과에 같은 내용이 있다.
- contradicted: 검색 결과가 주장과 다른 날짜·수치·사실을 말한다.
- unknown: 검색 결과로 판단할 수 없다. 애매하면 unknown.
검색 결과가 오래된 해의 정보일 수 있으니 연도를 주의한다."""

PLACE_MARK = {"found": "✅", "mentioned": "🟡", "elsewhere": "❌", "missing": "❌"}
PLACE_TEXT = {"found": "지역 검색에서 확인", "mentioned": "웹·블로그에 언급 있음 (장소 등록은 없음)",
              "elsewhere": "다른 지역에만 있음", "missing": "검색되지 않음 — 지어냈을 가능성"}
FACT_MARK = {"supported": "✅", "unknown": "⚠️", "contradicted": "❌", "error": "⚠️"}
FACT_TEXT = {"supported": "근거 있음", "unknown": "확인 불가", "contradicted": "검색 결과와 다름",
             "error": "검색 실패"}


@dataclass
class Report:
    region: str = ""
    places: list[tuple[str, str, list]] = field(default_factory=list)   # (이름, 상태, 근거)
    facts: list[tuple[str, str, str, list]] = field(default_factory=list)  # (주장, 판정, 이유, 근거)
    errors: list[str] = field(default_factory=list)

    @property
    def bad(self) -> int:
        return (sum(1 for _, st, _ in self.places if st in ("elsewhere", "missing"))
                + sum(1 for _, v, _, _ in self.facts if v == "contradicted"))

    def summary(self) -> str:
        p_ok = sum(1 for _, st, _ in self.places if st == "found")
        f_ok = sum(1 for _, v, _, _ in self.facts if v == "supported")
        return (f"장소 {p_ok}/{len(self.places)} 확인, 사실 {f_ok}/{len(self.facts)} 근거 있음, "
                f"문제 {self.bad}건")

    def to_markdown(self, title: str) -> str:
        out = [f"# 사실 확인 보고서 — {title}", "",
               "> 네이버 검색(NAVER API HUB) 결과로 자동 확인한 참고 자료입니다. "
               "사실 판정은 로컬 LLM 이 하므로 틀릴 수 있습니다. 발행 전 ❌·⚠️ 항목을 직접 확인하세요.", "",
               f"요약: {self.summary()}" + (f" (기준 지역: {self.region})" if self.region else ""), ""]
        if self.places:
            out += ["## 장소", "", "| 판정 | 장소 | 결과 | 근거 |", "|---|---|---|---|"]
            for name, st, hits in self.places:
                ev = f"{hits[0].title} ({hits[0].address or hits[0].link})" if hits else "-"
                out.append(f"| {PLACE_MARK[st]} | {name} | {PLACE_TEXT[st]} | {ev.replace('|', '/')} |")
            out.append("")
        if self.facts:
            out += ["## 사실", ""]
            for claim, v, reason, hits in self.facts:
                out.append(f"### {FACT_MARK[v]} {claim}")
                out.append(f"- 판정: {FACT_TEXT[v]} — {reason}")
                for h in hits[:3]:
                    out.append(f"- 출처: [{h.title}]({h.link})" + (f" ({h.date})" if h.date else ""))
                out.append("")
        if self.errors:
            out += ["## 확인 중 오류", ""] + [f"- {e}" for e in self.errors] + [""]
        return "\n".join(out)


def _json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def verify(markdown: str, model: str | None = None, region: str = "",
           progress=print) -> Report:
    rep = Report()
    # 확인 중에는 LLM 을 여러 번 부르므로 모델을 잠시 붙잡아 두고, 끝나면 내린다.
    try:
        res = llm.generate(markdown, model=model, system=EXTRACT_SYSTEM, temperature=0,
                           keep_alive="5m", fmt="json")
        items = _json(res["content"])
    except (llm.LLMError, json.JSONDecodeError) as e:
        rep.errors.append(f"확인 항목 추출 실패: {e}")
        llm.unload(model)
        return rep
    rep.region = region or str(items.get("region", "")).strip()
    places = [p for p in dict.fromkeys(str(x).strip() for x in items.get("places", [])) if p][:12]
    facts = [f for f in items.get("facts", []) if isinstance(f, dict) and f.get("claim")][:8]

    for name in places:
        try:
            st, hits = search.find_place(name, rep.region)
        except search.SearchError as e:
            rep.errors.append(f"{name}: {e}")
            continue
        rep.places.append((name, st, hits))
        progress(f"      {PLACE_MARK[st]} 장소 {name} — {PLACE_TEXT[st]}")

    for f in facts:
        claim = str(f["claim"]).strip()
        query = str(f.get("query") or claim).strip()
        try:
            hits = search.search("news", query, 5) + search.search("webkr", query, 5)
        except search.SearchError as e:
            rep.facts.append((claim, "error", str(e), []))
            continue
        if not hits:
            rep.facts.append((claim, "unknown", "검색 결과 없음", []))
            progress(f"      ⚠️ 사실 {claim[:40]} — 검색 결과 없음")
            continue
        evidence = "\n".join(f"- {h.title}: {h.desc}" + (f" ({h.date})" if h.date else "") for h in hits)
        try:
            j = _json(llm.generate(f"주장: {claim}\n\n검색 결과:\n{evidence}", model=model,
                                   system=JUDGE_SYSTEM, temperature=0, keep_alive="5m",
                                   fmt="json")["content"])
            v = j.get("verdict", "unknown")
            v = v if v in FACT_MARK else "unknown"
            reason = str(j.get("reason", "")).strip()
        except (llm.LLMError, json.JSONDecodeError) as e:
            v, reason = "error", f"판단 실패: {e}"
        rep.facts.append((claim, v, reason, hits))
        progress(f"      {FACT_MARK[v]} 사실 {claim[:40]} — {FACT_TEXT[v]}")

    llm.unload(model)
    return rep
