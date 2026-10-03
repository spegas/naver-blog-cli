# 작성: 송중호 (2026-10-03) — llm.py 의 원고 다듬기 테스트. Ollama 없이 돈다.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from naver_blog_cli import llm  # noqa: E402
from naver_blog_cli.core import split_title  # noqa: E402


def test_strips_fence_and_think():
    raw = "<think>생각</think>\n```markdown\n# 제목\n\n본문\n```"
    body, tags = llm.clean_markdown(raw)
    assert body == "# 제목\n\n본문\n"
    assert tags == []


def test_trailing_hashtags_become_tags():
    body, tags = llm.clean_markdown("# 제목\n\n본문 문단.\n\n#세종시산책 #가을나들이\n#힐링\n")
    assert body == "# 제목\n\n본문 문단.\n"
    assert tags == ["세종시산책", "가을나들이", "힐링"]


def test_heading_is_not_hashtag():
    body, tags = llm.clean_markdown("# 제목\n\n## 소제목\n")
    assert body.endswith("## 소제목\n")
    assert tags == []


def test_merge_tags_dedupes_and_removes_spaces():
    assert llm.merge_tags(["세종시", "가을 산책"], None, ["#세종시", "힐링"]) == \
        ["세종시", "가을산책", "힐링"]


def test_find_han():
    assert llm.find_han("가을 낙엽이满地인 길") == ["地", "满"]
    assert llm.find_han("시간이あっ실 지나갑니다") == ["あ", "っ"]
    assert llm.find_han("한국어만 있는 글") == []


def test_prompt_without_material_says_so():
    p = llm.build_prompt("", ["세종시"], 1000)
    assert "자료 없음" in p and "세종시" in p and "1000자" in p
    assert p.rstrip().endswith("쓰지 마세요.") and "한글" in p  # 언어 지시는 맨 끝에


def test_cleaned_output_splits_title():
    body, _ = llm.clean_markdown("```\n# 세종 산책\n\n본문\n```")
    title, rest = split_title(body)
    assert title == "세종 산책" and rest.strip() == "본문"


def test_foreign_sentences_ignores_parenthesized_hanja():
    text = "미식여행 '세종오식(世宗五食)'을 즐겨요. 도시의 번华中에서 쉬어요.\n한국어 문장."
    got = llm.foreign_sentences(text)
    assert len(got) == 1 and "번华中" in got[0]


def test_blank_only_outside_parens():
    assert llm._sub_outside_parens("시간이あっ실 가요. 세종오식(世宗五食)") == "시간이＿＿실 가요. 세종오식(世宗五食)"
