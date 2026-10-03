# 작성: 송중호 (2026-09-22) — 신규 파일. core.py(원작성자: jjorae, Johnhyeon —
#      https://github.com/Johnhyeon/naver-blog-mcp) 를 MCP 없이 터미널에서 바로
#      쓰기 위해 새로 작성했다.
"""MCP 없이 터미널에서 바로 실행하는 CLI.

core.py 에 있는 함수를 그대로 호출한다.
사전 준비는 README 의 "설치"·"로그인" 절과 같다:
  uv sync && uv run playwright install chromium
  uv run python login_setup.py

사용 예:
  NAVER_BLOG_ID=내블로그아이디 uv run naver-blog-cli list-drafts
  NAVER_BLOG_ID=내블로그아이디 uv run naver-blog-cli create-draft --title "제목" --file post.md
  NAVER_BLOG_ID=내블로그아이디 uv run naver-blog-cli publish-draft --confirm --title "제목"
  NAVER_BLOG_ID=내블로그아이디 uv run naver-blog-cli ai-draft --keywords 세종시,가을 --file 자료.txt

ai-draft / verify-draft 는 송중호가 2026-10-03 추가 (로컬 Ollama 로 원고 생성 → 네이버 검색 확인 → 임시저장;
llm.py, search.py, verify.py).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path

from . import core, llm, search, verify


def _split_tags(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    return tags or None


def _markdown_from_args(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).expanduser().read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("마크다운을 --file 로 주거나 표준입력으로 넘기세요.")


def _run(coro) -> None:
    print(asyncio.run(coro))


def cmd_check_session(args: argparse.Namespace) -> None:
    _run(core.check_session())


def cmd_list_categories(args: argparse.Namespace) -> None:
    _run(core.list_categories())


def cmd_list_drafts(args: argparse.Namespace) -> None:
    _run(core.list_drafts())


def cmd_create_draft(args: argparse.Namespace) -> None:
    markdown = _markdown_from_args(args)
    # 글 첫 줄이 '# 제목' 이면 --title 을 생략할 수 있다. 그 줄은 본문에서 뺀다
    # (ai-draft 가 저장한 원고를 고친 뒤 그대로 올릴 수 있게). — 송중호 2026-10-03
    head, body = core.split_title(markdown)
    title = args.title or head
    if not title:
        raise SystemExit("--title 을 주거나 글 첫 줄을 '# 제목' 으로 두세요.")
    if head and head == title:
        markdown = body
    _run(core.create_draft(
        title=title,
        markdown=markdown,
        category=args.category or "",
        tags=_split_tags(args.tags),
    ))


def cmd_create_draft_from_folder(args: argparse.Namespace) -> None:
    _run(core.create_draft_from_folder(
        folder=args.folder,
        markdown_file=args.markdown_file,
        title=args.title or "",
        category=args.category or "",
        tags=_split_tags(args.tags),
    ))


def cmd_publish_draft(args: argparse.Namespace) -> None:
    _run(core.publish_draft(
        confirm=args.confirm,
        title=args.title or "",
        visibility=args.visibility or "",
    ))


def cmd_delete_draft(args: argparse.Namespace) -> None:
    _run(core.delete_draft(
        confirm=args.confirm,
        title=args.title or "",
        index=args.index or 0,
    ))


def cmd_delete_post(args: argparse.Namespace) -> None:
    _run(core.delete_post(
        url_or_log_no=args.target,
        confirm=args.confirm,
    ))


def _read_lines_interactive(prompt: str) -> str:
    """여러 줄 입력. 빈 줄에서 엔터를 한 번 더 치면(빈 줄 두 번) 끝난다."""
    print(prompt)
    lines: list[str] = []
    try:
        while True:
            line = input()
            if not line and lines and not lines[-1]:
                break
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).strip()


def _material_from_args(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.file:
        return Path(args.file).expanduser().read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return _read_lines_interactive(
        "블로그 글의 바탕이 될 문장(자료)을 입력하세요. 끝내려면 빈 줄에서 엔터를 두 번 누르세요.\n"
        "(자료 없이 키워드만으로 쓰려면 바로 엔터 두 번)")


def _save_draft_file(markdown: str, title: str, out: str | None) -> Path:
    if out:
        path = Path(out).expanduser()
    else:
        slug = re.sub(r"[^\w가-힣]+", "_", title).strip("_")[:40] or "draft"
        path = Path("drafts") / f"{time.strftime('%Y%m%d-%H%M%S')}_{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def _step(msg: str) -> None:
    print(msg, flush=True)


def _run_verify(markdown: str, title: str, path: Path, model: str, region: str):
    """원고를 검색으로 확인하고 보고서를 원고 옆에 저장한다. 검색 키가 없으면 None."""
    if not search.available():
        _step("      확인 건너뜀: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다.")
        return None
    rep = verify.verify(markdown, model=model, region=region, progress=_step)
    out = path.with_name(path.stem + "_확인.md")
    out.write_text(rep.to_markdown(title), encoding="utf-8")
    _step(f"      {rep.summary()}")
    _step(f"      보고서: {out}")
    return rep


def cmd_ai_draft(args: argparse.Namespace) -> None:
    material = _material_from_args(args)
    keywords = _split_tags(args.keywords)
    if keywords is None and sys.stdin.isatty():
        keywords = _split_tags(input("키워드를 쉼표로 구분해 입력하세요 (예: 세종시,가을,산책): "))
    if not material and not keywords:
        raise SystemExit("자료 문장이나 키워드 중 하나는 있어야 합니다.")
    model = args.model or llm.model_name()

    if args.search:
        query = args.search_query or " ".join(keywords or [])
        _step(f"[검색] 네이버에서 '{query}' 자료 수집 중...")
        try:
            found, hits = search.gather_material(query)
            material = (material + "\n\n" + found).strip()
            _step(f"      검색 결과 {len(hits)}건을 자료로 사용")
        except search.SearchError as e:
            _step(f"      검색 건너뜀: {e}")

    _step(f"[생성] {model} 로 원고 생성 중... (보통 1~2분)")
    try:
        res = llm.generate(llm.build_prompt(material, keywords or [], args.length, args.request),
                           model=model)
    except llm.LLMError as e:
        raise SystemExit(f"원고 생성 실패: {e}")
    markdown, model_tags = llm.clean_markdown(res["content"])

    title, body = core.split_title(markdown)
    title = args.title or title or (keywords[0] if keywords else "제목 없음")
    tags = llm.merge_tags(keywords, _split_tags(args.tags), model_tags)
    if llm.foreign_sentences(body):
        _step("[교정] 한자/일본어가 섞인 문장을 한국어로 고치는 중...")
        body, n = llm.fix_foreign(body, model=model)
        _step(f"      {n}문장 고침")
    path = _save_draft_file(f"# {title}\n\n{body}", title, args.out)
    _step(f"[저장] {path}  ({len(body)}자, {res['seconds']:.0f}초)")
    _step(f"      제목: {title}")
    _step(f"      태그: {', '.join(tags) if tags else '(없음)'}")
    left = llm.foreign_sentences(body)
    if left:
        _step(f"      주의: 한자/일본어가 남은 문장 {len(left)}개 — 임시저장 뒤 확인하세요: "
              + " / ".join(x.strip()[:30] for x in left[:3]))

    rep = None
    if args.verify:
        _step("[확인] 장소·사실을 네이버 검색으로 확인 중...")
        rep = _run_verify(body, title, path, model, args.region)
    else:
        _step("      주의: 로컬 모델은 장소·날짜 같은 사실을 지어낼 수 있습니다. 발행 전 꼭 확인하세요.")

    upload_cmd = (f'uv run naver-blog-cli create-draft --file "{path}"'
                  + (f" --category {args.category}" if args.category else "")
                  + (f" --tags {','.join(tags)}" if tags else ""))
    if args.dry_run:
        _step("[임시저장] --dry-run: 올리지 않았습니다. 원고를 고친 뒤 이렇게 올리세요:")
        _step(f"      {upload_cmd}")
        return
    if rep and rep.bad and not args.upload_anyway:
        _step(f"[임시저장] 확인에서 문제 {rep.bad}건이 나와 올리지 않았습니다. "
              "보고서를 보고 원고를 고친 뒤 이렇게 올리세요 (그대로 올리려면 --upload-anyway):")
        _step(f"      {upload_cmd}")
        return
    _step("[임시저장] 네이버 블로그에 임시저장 중... (발행하지 않음)")
    _run(core.create_draft(title=title, markdown=body, category=args.category or "", tags=tags or None))


def cmd_verify_draft(args: argparse.Namespace) -> None:
    path = Path(args.file).expanduser()
    head, body = core.split_title(path.read_text(encoding="utf-8"))
    model = args.model or llm.model_name()
    _step(f"[확인] {path.name} 의 장소·사실을 네이버 검색으로 확인 중... ({model})")
    if not _run_verify(body, head or path.stem, path, model, args.region):
        raise SystemExit(1)


def _readonly() -> bool:
    """NAVER_BLOG_READONLY 가 켜져 있으면 발행·삭제 명령을 아예 등록하지 않는다.

    원본(server.py)의 READONLY 모드와 같은 동작이다: 부르지 못하게 막는 가장
    확실한 방법은 명령 목록에 없는 것이다.
    """
    return os.getenv("NAVER_BLOG_READONLY", "").lower() not in ("", "0", "false", "no")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="naver-blog-cli",
        description="MCP 없이 네이버 블로그를 직접 조작하는 CLI. "
                    "NAVER_BLOG_ID 환경변수가 필요하다.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check-session", help="로그인 세션이 살아있는지 확인")
    s.set_defaults(func=cmd_check_session)

    s = sub.add_parser("list-categories", help="블로그 카테고리 목록 조회 (발행하지 않음)")
    s.set_defaults(func=cmd_list_categories)

    s = sub.add_parser("list-drafts", help="임시저장 글 목록 조회 (최신순)")
    s.set_defaults(func=cmd_list_drafts)

    s = sub.add_parser("create-draft", help="마크다운으로 글을 작성해 임시저장 (발행하지 않음)")
    s.add_argument("--title", default="", help="비우면 글 첫 줄('# 제목') 을 제목으로 쓴다")
    s.add_argument("--file", help="마크다운 파일 경로 (없으면 표준입력에서 읽음)")
    s.add_argument("--category", default="")
    s.add_argument("--tags", help="쉼표로 구분한 태그, 예: 여행,세종시")
    s.set_defaults(func=cmd_create_draft)

    s = sub.add_parser(
        "ai-draft",
        help="로컬 LLM(Ollama)으로 자료 문장+키워드에서 원고를 만들어 임시저장 (발행하지 않음)",
    )
    src = s.add_mutually_exclusive_group()
    src.add_argument("--text", help="자료 문장 (없으면 --file, 표준입력, 대화형 입력 순)")
    src.add_argument("--file", help="자료 문장이 든 텍스트/마크다운 파일")
    s.add_argument("--keywords", help="쉼표로 구분한 키워드. 원고에 넣고 태그로도 쓴다")
    s.add_argument("--category", default="")
    s.add_argument("--tags", help="키워드 외에 더 붙일 태그 (쉼표 구분)")
    s.add_argument("--title", default="", help="비우면 모델이 지은 제목을 쓴다")
    s.add_argument("--model", default="",
                   help=f"Ollama 모델 (기본: NAVER_LLM_MODEL 또는 {llm.DEFAULT_MODEL})")
    s.add_argument("--length", type=int, default=1500, help="목표 분량(자), 기본 1500")
    s.add_argument("--request", default="", help="추가 요청, 예: '가족 나들이 위주로'")
    s.add_argument("--out", help="원고 저장 경로 (기본: drafts/날짜_제목.md)")
    s.add_argument("--dry-run", action="store_true",
                   help="원고만 만들어 저장하고 네이버에는 올리지 않음")
    s.add_argument("--search", action="store_true",
                   help="쓰기 전에 키워드로 네이버(뉴스·웹문서·블로그)를 검색해 자료로 쓴다")
    s.add_argument("--search-query", default="", help="--search 검색어 (기본: 키워드를 이어 붙임)")
    s.add_argument("--verify", action="store_true",
                   help="쓴 뒤 장소·사실을 네이버 검색으로 확인해 보고서를 만든다. 문제가 있으면 올리지 않음")
    s.add_argument("--region", default="", help="확인 기준 지역, 예: 세종시 (기본: 원고에서 추정)")
    s.add_argument("--upload-anyway", action="store_true", help="--verify 에서 문제가 나와도 임시저장")
    s.set_defaults(func=cmd_ai_draft)

    s = sub.add_parser("verify-draft", help="마크다운 원고의 장소·사실을 네이버 검색으로 확인 (올리지 않음)")
    s.add_argument("file")
    s.add_argument("--region", default="", help="확인 기준 지역, 예: 세종시 (기본: 원고에서 추정)")
    s.add_argument("--model", default="", help=f"Ollama 모델 (기본: {llm.DEFAULT_MODEL})")
    s.set_defaults(func=cmd_verify_draft)

    s = sub.add_parser(
        "create-draft-from-folder",
        help="글과 이미지가 같은 폴더에 있을 때 폴더째 임시저장 (발행하지 않음)",
    )
    s.add_argument("folder")
    s.add_argument("--markdown-file", default="post.md")
    s.add_argument("--title", default="", help="비우면 글 첫 줄('# 제목') 또는 meta.json 사용")
    s.add_argument("--category", default="")
    s.add_argument("--tags", help="쉼표로 구분한 태그")
    s.set_defaults(func=cmd_create_draft_from_folder)

    # 발행·삭제는 되돌리기 어렵다. NAVER_BLOG_READONLY 가 켜져 있으면 명령 자체를
    # 등록하지 않는다 (원본 server.py 의 READONLY 모드와 동일한 동작).
    if not _readonly():
        s = sub.add_parser("publish-draft", help="임시저장 글을 발행 — 되돌릴 수 없음")
        s.add_argument("--confirm", action="store_true", required=True,
                       help="발행을 실제로 실행하려면 반드시 지정")
        s.add_argument("--title", default="", help="발행할 임시저장 글 제목 (부분 일치 가능)")
        s.add_argument("--visibility", default="",
                       choices=["", "public", "neighbor", "both_neighbor", "private"])
        s.set_defaults(func=cmd_publish_draft)

        s = sub.add_parser("delete-draft", help="임시저장 글 삭제 — 되돌릴 수 없음")
        s.add_argument("--confirm", action="store_true", required=True,
                       help="삭제를 실제로 실행하려면 반드시 지정")
        s.add_argument("--title", default="")
        s.add_argument("--index", type=int, default=0, help="list-drafts 순번 (1이 최신)")
        s.set_defaults(func=cmd_delete_draft)

        s = sub.add_parser("delete-post", help="발행된 글 삭제 — 되돌릴 수 없음")
        s.add_argument("target", help="글 URL 또는 글 번호(logNo)")
        s.add_argument("--confirm", action="store_true", required=True,
                       help="삭제를 실제로 실행하려면 반드시 지정")
        s.set_defaults(func=cmd_delete_post)

    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
