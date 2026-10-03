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
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from . import core


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
    _run(core.create_draft(
        title=args.title,
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
    s.add_argument("--title", required=True)
    s.add_argument("--file", help="마크다운 파일 경로 (없으면 표준입력에서 읽음)")
    s.add_argument("--category", default="")
    s.add_argument("--tags", help="쉼표로 구분한 태그, 예: 여행,세종시")
    s.set_defaults(func=cmd_create_draft)

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
