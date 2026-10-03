# 작성: 송중호 (2026-10-03) — 신규 파일. 로컬 Ollama 로 블로그 원고(마크다운)를 만든다.
"""로컬 LLM(Ollama) 으로 블로그 원고를 만든다.

사용자가 준 자료(문장)와 키워드로 마크다운 원고를 만들고, 그 결과를 core.create_draft 에
그대로 넘긴다. 외부 패키지 없이 표준 라이브러리(urllib)로 Ollama HTTP API 를 부른다.

27B 급 로컬 모델은 지역 정보 같은 세부 사실을 지어낸다 (2026-10-03 실측: 세종시 글에
수원 공원 이름을 씀). 그래서 프롬프트는 "자료에 있는 사실만" 쓰게 하고, 자료가 없으면
일반적인 내용만 쓰도록 묶는다. 사람이 임시저장 글을 확인한 뒤 발행하는 흐름이 전제다.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_MODEL = "qwen3.6:27b"
DEFAULT_HOST = "http://localhost:11434"


class LLMError(RuntimeError):
    pass


def model_name() -> str:
    return os.environ.get("NAVER_LLM_MODEL", DEFAULT_MODEL)


def host() -> str:
    return os.environ.get("OLLAMA_HOST", DEFAULT_HOST).rstrip("/")


SYSTEM = """너는 한국어 네이버 블로그 글을 쓰는 작가다. 모든 글은 반드시 한글(한국어)로 쓴다.
규칙:
- 반드시 마크다운으로만 답한다. 설명, 인사, 코드펜스(```) 없이 원고만 출력한다.
- 첫 줄은 '# 제목' 한 줄이다. 제목도 한글로 쓴다.
- 존댓말(~습니다, ~해요)로 쓴다.
- 한글만 쓴다. 한자(漢字)·중국어·일본어 글자를 한 글자도 섞지 않는다.
  한자어는 한글로 적는다 (예: '方面' → '면', '满地' → '가득', '贅沢' → '호사').
  자료에 영어·한자 표기가 있어도 본문은 한글로 옮겨 쓴다. 고유명사의 영문 표기만 예외다.
- 소제목은 '## ', 필요하면 목록과 표(GFM 파이프)를 쓴다.
- 인라인 코드(`)와 HTML 태그는 쓰지 않는다. 인용문(>)과 표 안에는 링크를 넣지 않는다.
- 사실(장소 이름, 주소, 날짜, 운영시간, 요금, 수치)은 '자료'에 있는 것만 쓴다.
  자료에 없는 사실은 지어내지 말고, 일반적인 감상이나 팁으로 채운다.
- 해시태그는 본문에 쓰지 않는다 (태그는 따로 붙인다)."""


def build_prompt(material: str, keywords: list[str], length: int = 1500,
                 extra: str = "") -> str:
    parts = []
    if keywords:
        parts.append("키워드: " + ", ".join(keywords)
                     + "\n(키워드는 제목과 본문에 자연스럽게 넣는다)")
    parts.append(f"분량: {length}자 안팎")
    if extra:
        parts.append("추가 요청: " + extra)
    material = material.strip()
    parts.append("자료:\n" + (material if material else "(자료 없음 — 키워드에 대한 일반적인 내용만 쓴다)"))
    # 로컬 모델은 마지막 지시를 가장 잘 따른다. 자료(검색 결과)가 길면 시스템 프롬프트의
    # 언어 규칙을 잊고 한자를 섞어서, 끝에 한 번 더 못 박는다.
    parts.append("위 자료를 바탕으로 블로그 원고를 반드시 한글(한국어)로만 작성해 주세요. "
                 "한자·중국어·일본어 글자는 쓰지 마세요.")
    return "\n\n".join(parts)


_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", re.S)
_HASHTAG_LINE = re.compile(r"^\s*(#[^\s#]+\s*)+$")
# 한자(CJK 통합 한자)와 일본어 가나. 한국어 원고에 섞이면 거의 항상 모델의 언어 혼선이다
# (2026-10-03 실측: qwen3.6 이 "方面", "あっ" 을 섞음).
_HAN = re.compile("[\\u4e00-\\u9fff\\u3400-\\u4dbf\\u3040-\\u309f\\u30a0-\\u30ff]")


def clean_markdown(text: str) -> tuple[str, list[str]]:
    """모델 출력을 원고로 다듬는다. (본문, 본문에서 떼어낸 해시태그) 를 돌려준다.

    - <think> 블록과 감싼 코드펜스를 벗긴다.
    - 끝에 붙은 해시태그 줄은 떼어 태그로 돌린다. 본문에 두면 글자로 그대로 찍힌다.
    """
    text = _THINK.sub("", text).strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1).strip()
    lines = text.splitlines()
    tags: list[str] = []
    while lines and (not lines[-1].strip() or _HASHTAG_LINE.match(lines[-1])):
        line = lines.pop()
        tags = [t.lstrip("#") for t in line.split() if t.startswith("#")] + tags
    return "\n".join(lines).strip() + "\n", tags


_PAREN = re.compile(r"\([^()]*\)")
_SENT = re.compile(r"[^.!?\n]*[.!?]?")

FIX_SYSTEM = """너는 한국어 교정 도우미다. 문장에서 깨진 부분이 ＿＿ 로 표시돼 있다.
문맥에 맞는 자연스러운 한국어로 ＿＿ 를 채워 문장을 완성한다. 어색하면 ＿＿ 바로 앞뒤의
몇 글자까지 함께 고쳐도 된다. 나머지 내용, 마크다운 기호는 그대로 둔다.
완성한 문장 하나만 출력한다. ＿＿ 나 한자·일본어 글자를 남기지 않는다."""
_HAN_RUN = re.compile("[\\u4e00-\\u9fff\\u3400-\\u4dbf\\u3040-\\u309f\\u30a0-\\u30ff]+")


def _sub_outside_parens(sent: str) -> str:
    """괄호 밖의 한자·가나 덩어리만 ＿＿ 로 바꾼다."""
    out, depth = [], 0
    for part in re.split(r"([()])", sent):
        if part == "(":
            depth += 1
        elif part == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            part = _HAN_RUN.sub("＿＿", part)
        out.append(part)
    return "".join(out)


def foreign_sentences(text: str) -> list[str]:
    """괄호 밖에 한자·가나가 섞인 문장들. 괄호 안 표기('세종오식(世宗五食)')는 원문 병기라 둔다."""
    out = []
    for sent in _SENT.findall(text):
        if sent.strip() and _HAN.search(_PAREN.sub("", sent)):
            out.append(sent)
    return list(dict.fromkeys(out))


def fix_foreign(text: str, model: str | None = None) -> tuple[str, int]:
    """한자·가나가 섞인 문장만 모델에게 다시 쓰게 해 바꿔 끼운다. (고친 글, 고친 문장 수)

    글 전체를 다시 쓰게 하면 다른 곳까지 바뀌므로 문장 단위로만 고친다.
    고친 문장에도 여전히 섞여 있으면 원래 문장을 둔다 (경고는 호출한 쪽이 다시 띄운다).
    """
    fixed = 0
    for sent in foreign_sentences(text):
        try:
            # 섞인 글자를 보여주면 모델이 그대로 따라 쓴다 (2026-10-03 실측: 'あっ', '满地' 를
            # 지정해 줘도 원문 그대로 돌려줌). 그래서 그 자리를 빈칸으로 바꿔 문맥으로 채우게 한다.
            # 괄호 안 병기('세종오식(世宗五食)')는 건드리지 않는다.
            blanked = _sub_outside_parens(sent.strip())
            new = generate(f"문장: {blanked}", model=model, system=FIX_SYSTEM,
                           temperature=0, keep_alive="5m", num_ctx=2048)["content"].strip()
            new = re.sub(r"^(고친 )?문장\s*:\s*", "", new)
        except LLMError:
            continue
        new = _THINK.sub("", new).strip().splitlines()[0] if new else ""
        if new and "＿" not in new and not _HAN.search(_PAREN.sub("", new)):
            lead = sent[:len(sent) - len(sent.lstrip())]
            text = text.replace(sent, lead + new, 1)
            fixed += 1
    unload(model)
    return text, fixed


def find_han(text: str) -> list[str]:
    """원고에 섞인 한자·가나를 돌려준다 (경고용)."""
    return sorted(set(_HAN.findall(text)))


def merge_tags(*groups: list[str] | None, limit: int = 30) -> list[str]:
    """순서를 지키며 중복 없이 합친다. 네이버 태그는 공백을 못 가지므로 붙인다."""
    seen, out = set(), []
    for g in groups:
        for t in g or []:
            t = t.strip().lstrip("#").replace(" ", "")
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out[:limit]


def generate(prompt: str, model: str | None = None, num_ctx: int = 16384,
             temperature: float = 0.7, timeout: float = 1800, system: str = SYSTEM,
             keep_alive: int | str = 0, fmt: str | None = None) -> dict:
    """Ollama /api/chat 을 한 번 부른다.

    keep_alive=0(기본): 답을 받자마자 모델을 메모리에서 내린다. 바로 이어서 브라우저(Playwright)
    를 띄우므로, 18GB 모델을 붙잡아 두면 32GB 맥에서 여유가 빠듯해진다 (2026-10-03 실측).
    """
    payload = {
        "model": model or model_name(),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "keep_alive": keep_alive,
        "options": {"num_ctx": num_ctx, "temperature": temperature},
    }
    if fmt:
        payload["format"] = fmt  # "json" 이면 Ollama 가 JSON 으로만 답하게 묶는다
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{host()}/api/chat", body,
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 404:
            raise LLMError(f"모델이 없습니다: {model or model_name()} — "
                           f"`ollama pull {model or model_name()}` 로 받으세요. ({detail})")
        raise LLMError(f"Ollama 오류 {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LLMError(f"Ollama 에 연결하지 못했습니다 ({host()}). Ollama 앱이 켜져 있는지 확인하세요. ({e.reason})")
    content = (data.get("message") or {}).get("content", "")
    if not content.strip():
        raise LLMError("모델이 빈 답을 돌려줬습니다.")
    return {"content": content,
            "eval_count": data.get("eval_count", 0),
            "seconds": data.get("total_duration", 0) / 1e9}


def unload(model: str | None = None) -> None:
    """모델을 메모리에서 내린다. 실패해도 조용히 넘어간다 (다음 단계를 막지 않게)."""
    body = json.dumps({"model": model or model_name(), "keep_alive": 0}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{host()}/api/generate", body, {"Content-Type": "application/json"}), timeout=30).read()
    except Exception:
        pass
