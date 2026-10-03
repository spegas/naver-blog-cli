# 작성: 송중호 (2026-10-03) — 신규 파일. 네이버 검색 API(NAVER API HUB) 호출.
"""네이버 검색 API 로 원고 자료를 모으고 사실 확인 근거를 찾는다.

네이버 검색 API 는 2026년 개발자센터(openapi.naver.com)에서 네이버클라우드의
NAVER API HUB 로 옮겨졌다. 주소와 인증 헤더가 바뀌었다:
  주소: https://naverapihub.apigw.ntruss.com/search/v1/{blog,news,webkr,local,...}
  헤더: X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
키는 네이버클라우드 콘솔 > AI·NAVER API > Application 에서 받고, 환경변수
NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 로만 읽는다 (코드·저장소에 넣지 말 것).

google.com 은 쓰지 않는다. curl 로는 자바스크립트 요구 페이지만 오고, Playwright 로는
첫 요청부터 /sorry/ 캡차로 막혔다 (2026-10-03 실측). 약관상으로도 자동 수집이 금지다.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE = "https://naverapihub.apigw.ntruss.com/search/v1"
# 지역 검색은 한 번에 최대 5건만 준다 (API 제한).
MAX_DISPLAY = {"local": 5}


class SearchError(RuntimeError):
    pass


@dataclass
class Hit:
    kind: str
    title: str
    desc: str
    link: str
    address: str = ""
    category: str = ""
    date: str = ""


def available() -> bool:
    return bool(os.environ.get("NAVER_CLIENT_ID") and os.environ.get("NAVER_CLIENT_SECRET"))


_TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    """검색 결과의 <b> 강조 태그와 HTML 엔티티(&quot; 등)를 벗긴다."""
    return html.unescape(_TAG.sub("", text or "")).strip()


def search(kind: str, query: str, display: int = 5, timeout: float = 10) -> list[Hit]:
    if not available():
        raise SearchError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다.")
    display = min(display, MAX_DISPLAY.get(kind, 100))
    url = f"{BASE}/{kind}?" + urllib.parse.urlencode({"query": query, "display": display})
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NAVER_CLIENT_SECRET"],
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        if e.code in (401, 403):
            raise SearchError(f"인증 실패({e.code}) — NAVER API HUB 키와 검색 API 선택 여부를 확인하세요. {detail}")
        if e.code == 429:
            raise SearchError("호출 한도 초과(429). 잠시 뒤 다시 시도하세요.")
        raise SearchError(f"검색 오류 {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SearchError(f"검색 서버에 연결하지 못했습니다: {e.reason}")
    hits = []
    for it in data.get("items", []):
        hits.append(Hit(
            kind=kind,
            title=clean(it.get("title", "")),
            desc=clean(it.get("description", "")),
            link=it.get("originallink") or it.get("link", ""),
            address=it.get("roadAddress") or it.get("address", ""),
            category=it.get("category", ""),
            date=it.get("pubDate") or it.get("postdate", ""),
        ))
    return hits


def gather_material(query: str, per_kind: int = 5) -> tuple[str, list[Hit]]:
    """뉴스·웹문서·블로그를 검색해 원고 자료 텍스트로 묶는다. (자료, 출처 목록)

    한 종류가 실패해도 나머지로 진행한다. 전부 실패하면 SearchError.
    """
    hits: list[Hit] = []
    errors = []
    for kind in ("news", "webkr", "blog"):
        try:
            hits += search(kind, query, per_kind)
        except SearchError as e:
            errors.append(f"{kind}: {e}")
    if not hits:
        raise SearchError("; ".join(errors) or "검색 결과가 없습니다.")
    label = {"news": "뉴스", "webkr": "웹문서", "blog": "블로그"}
    lines = [f"(네이버 검색 결과: '{query}'. 출처마다 내용이 다를 수 있고, 날짜가 오래된 것은 지난 정보일 수 있다)"]
    for h in hits:
        date = f", {h.date}" if h.date else ""
        lines.append(f"- [{label[h.kind]}{date}] {h.title}: {h.desc}")
    return "\n".join(lines), hits


def _norm(s: str) -> str:
    return re.sub(r"[\s·\-_()\[\]]", "", s).lower()


def region_key(region: str) -> str:
    """'세종시' → '세종'. 주소('세종특별자치시 ...')와 비교하려고 행정단위 꼬리를 뗀다."""
    region = region.strip()
    return re.sub(r"(특별자치시|특별자치도|광역시|특별시|시|군|구|도)$", "", region) or region


def find_place(name: str, region: str = "") -> tuple[str, list[Hit]]:
    """장소가 실제로 있는지 본다. ('found' | 'elsewhere' | 'mentioned' | 'missing', 근거)

    found: 지역 검색에 그 이름이 있고, region 을 줬다면 주소도 그 지역.
    elsewhere: 이름은 있는데 주소가 다른 지역 (예: 세종시 글에 수원 '서수원호수공원').
    mentioned: 지역 검색엔 없지만 웹문서·블로그에 그 이름이 나옴 (산책로·다리처럼
               업체 등록이 안 되는 곳일 수 있다).
    missing: 어디에도 그 이름이 없음 — 지어냈을 가능성이 높다.
    """
    key = _norm(name)
    rkey = region_key(region)
    local = search("local", f"{region} {name}".strip(), 5)
    named = [h for h in local if key in _norm(h.title) or _norm(h.title) in key]
    if not named and rkey:
        # 지역명을 붙이면 엉뚱한 근처 가게가 나오기도 해서, 이름만으로 한 번 더 본다.
        named = [h for h in search("local", name, 5) if key in _norm(h.title) or _norm(h.title) in key]
    if named and (not rkey or any(rkey in h.address for h in named)):
        return "found", [h for h in named if not rkey or rkey in h.address]
    # 따옴표(정확히 일치) 검색만 하면 '금강 종주 자전거길' 같은 실제 이름을 놓친다
    # (2026-10-03 실측). 따옴표 없는 검색도 함께 본다.
    other = (search("webkr", f'"{name}"', 5) + search("webkr", name, 5)
             + search("blog", f"{region} {name}".strip(), 5))
    hit = [h for h in other if key in _norm(h.title + h.desc)]
    # 이름이 다른 지역 업체와 겹칠 수 있다 (예: '금강수목원' → 서울의 '금강수목원아파트').
    # 그 지역과 함께 언급된 글이 있으면 다른 지역이라고 단정하지 않는다.
    in_region = [h for h in hit if not rkey or rkey in h.title + h.desc]
    if in_region:
        return "mentioned", in_region
    if named:
        return "elsewhere", named
    if hit:
        return "mentioned", hit
    return "missing", []
