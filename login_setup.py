# 원작성자: jjorae <raehyeok.cho@gmail.com> (2026-08-27)
# 출처: https://github.com/Johnhyeon/naver-blog-mcp
# 수정: 송중호 (2026-10-03) — '로그인 상태 유지' 안내와, 체크 안 하고 로그인했을 때 경고 추가
"""최초 1회. 사람이 직접 로그인하고 쿠키만 덤프한다.

CAPTCHA, 2차인증, 기기등록 전부 사람이 처리한다.
자동화가 로그인을 흉내내지 않으므로 봇 탐지에 걸릴 표면이 거의 없다.
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# 서버와 같은 경로를 쓴다. 예전에는 여기만 하드코딩돼 있어서, NAVER_STATE 를 설정하면
# 로그인은 성공하는데 서버는 다른 곳을 보는 바람에 "세션 파일 없음" 이 떴다.
sys.path.insert(0, str(Path(__file__).parent / "src"))
from naver_blog_cli.session import STATE as OUT, save_state_file


AUTH = {"NID_AUT", "NID_SES"}


async def wait_login(ctx, timeout: float = 300.0) -> bool:
    """인증 쿠키가 생길 때까지 기다린다. 엔터 입력을 쓰지 않는 이유는,
    터미널 없이(백그라운드로) 띄워도 로그인만 하면 끝나게 하려는 것이다.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        names = {c["name"] for c in await ctx.cookies()}
        if AUTH & names:
            await asyncio.sleep(1.5)  # 나머지 쿠키까지 실린 뒤에 덤프
            return True
        await asyncio.sleep(2)
    return False


async def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = await ctx.new_page()
        await page.goto("https://nid.naver.com/nidlogin.login")

        print("=" * 60)
        print("브라우저에서 직접 로그인하세요. 로그인되면 자동으로 저장하고 닫습니다.")
        print("★ 로그인 버튼을 누르기 전에 '로그인 상태 유지' 를 꼭 체크하세요.")
        print("  체크하지 않으면 몇 시간 뒤 글쓰기만 재로그인을 요구합니다 (보기는 됨).")
        print("5분 안에 로그인하지 않으면 아무것도 저장하지 않고 끝납니다.")
        print("=" * 60)
        if not await wait_login(ctx):
            print("로그인 확인 못 함 — 저장하지 않고 종료합니다.")
            await browser.close()
            return

        await ctx.storage_state(path=str(OUT))
        save_state_file(OUT)
        print(f"저장됨: {OUT.resolve()}")
        # '로그인 상태 유지' 를 체크하면 NID_AUT 에 만료일이 붙는다. 없으면(세션 쿠키)
        # 브라우저를 닫는 순간 끝나는 로그인이라, 네이버가 몇 시간 뒤 글쓰기에서 재로그인을
        # 요구한다 (2026-10-03 실측: 약 2.5시간 뒤 에디터만 로그인 페이지로 바뀜).
        aut = [c for c in await ctx.cookies() if c["name"] == "NID_AUT"]
        if aut and aut[0].get("expires", -1) < 0:
            print("⚠ '로그인 상태 유지' 가 꺼진 채 로그인했습니다. 몇 시간 뒤 글쓰기가 막힐 수 있으니")
            print("  다시 실행해서 체크하고 로그인하는 것을 권합니다.")
        print("이 파일은 계정 접근권한 그 자체입니다. git 에 절대 올리지 마세요.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
