# naver-blog-cli

> 원작성자: jjorae \<raehyeok.cho@gmail.com\> (최초 커밋, 2026-08-27) /
> Johnhyeon \<whdqja216772@gmail.com\> (기능 확장) —
> 원본 저장소: [github.com/Johnhyeon/naver-blog-mcp](https://github.com/Johnhyeon/naver-blog-mcp)
> (그 원본: [github.com/jjorae/naver-blog-mcp](https://github.com/jjorae/naver-blog-mcp)) — MIT 라이선스
>
> 수정: 송중호 (2026-09-22) — MCP 서버(`server.py`) 제거, `core.py` + `cli.py` 구조로
> 변경해 MCP 클라이언트 없이 터미널에서 바로 쓰도록 만듦. 폴더/패키지명도
> `naver-blog-mcp` → `naver-blog-cli` 로 변경 (mcp 단어 제거). 기능 로직 자체는 그대로다.

네이버 블로그에 **서식·이미지·표·수식·장소가 들어간 글**을 쓰는 CLI.
Playwright로 스마트에디터 ONE을 직접 조작합니다.

마크다운을 주면 임시저장까지 해주고, 발행은 별도 툴로 분리돼 있습니다.

```markdown
## 오늘의 기록

**굵게** 와 [링크](https://naver.com) 가 들어간 문단.

- 목록도
- 됩니다

| 항목 | 지원 |
|------|------|
| 표   | O    |

![캡션](/path/photo.png)

:::file /path/report.pdf:::
:::formula x^2 + y^2 = z^2:::
:::place 강남역:::
```

---

## 먼저 읽어주세요

- **네이버 계정으로 로그인한 브라우저를 자동 조작합니다.** 과도하게 쓰면 계정이
  제재될 수 있습니다. 대량 자동 포스팅 용도로 만들지 않았고, 그런 기능을 넣지 마세요.
- **비밀번호는 저장하지 않습니다.** 사람이 직접 로그인해서 만든 쿠키 파일만 읽습니다.
- 그 쿠키 파일(`playwright-state/storage_state.json`)은 **계정 접근권한 그 자체**입니다.
  `.gitignore`에 들어 있지만, 실수로 공유하지 않도록 주의하세요.
- 네이버가 에디터를 바꾸면 깨질 수 있습니다. 그때는 `verify_selectors.py`로 진단합니다
  (아래 "셀렉터가 깨졌을 때").

## 요구사항

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- 네이버 블로그 계정

## 설치 (가상환경)

```bash
git clone <이 저장소>
cd naver-blog-cli
uv sync                          # .venv 를 만들고 의존성(playwright 등)을 설치
uv run playwright install chromium   # Playwright 가 쓰는 Chromium 브라우저 설치
```

`uv sync`가 프로젝트 폴더 안에 `.venv/`(가상환경)를 **자동으로 생성**합니다.
따로 `python -m venv` 를 만들 필요가 없습니다. 두 가지 방식으로 쓸 수 있습니다:

- **`uv run <명령>`** — 가상환경을 활성화하지 않고 그때그때 그 안에서 실행 (권장, 아래 예시가 전부 이 방식).
- **직접 활성화** — 한 셸에서 여러 명령을 계속 칠 때 편합니다.
  ```bash
  source .venv/bin/activate    # 이후 uv run 없이 naver-blog-cli, python 을 바로 씀
  naver-blog-cli --help
  deactivate                   # 빠져나오기
  ```

새 의존성이 `pyproject.toml`에 추가되면 `uv sync`를 다시 돌리면 됩니다 — `.venv`를 지우고
새로 만들 필요는 없습니다(단, 폴더 경로 자체를 옮겼다면 `.venv`가 옛 경로를 참조하므로
`rm -rf .venv && uv sync`로 다시 만드세요).

## 로그인 (최초 1회)

```bash
uv run python login_setup.py
```

브라우저가 열리면 **직접 로그인**하고 본인 블로그 홈까지 이동한 뒤 터미널에서 엔터를 치세요.
CAPTCHA·2차인증·기기등록은 전부 사람이 처리합니다.
쿠키가 `playwright-state/storage_state.json`에 저장되고, CLI는 그 파일만 읽습니다.

세션이 만료되면 이 명령을 다시 실행하면 됩니다.

## CLI 사용법

```bash
export NAVER_BLOG_ID=<블로그아이디>

uv run naver-blog-cli check-session
uv run naver-blog-cli list-categories
uv run naver-blog-cli list-drafts

# 마크다운 파일로 임시저장 (발행하지 않음)
uv run naver-blog-cli create-draft --title "제목" --file post.md --category 여행 --tags 여행,세종시
# 글 첫 줄이 '# 제목' 이면 --title 생략 가능 (그 줄은 본문에서 빠짐)
uv run naver-blog-cli create-draft --file post.md --category 여행

# 로컬 LLM(Ollama)으로 자료 문장+키워드 → 원고 생성 → 임시저장
uv run naver-blog-cli ai-draft --keywords 세종시,가을,산책 --category 휴식
# 네이버 검색으로 자료 수집 + 쓴 뒤 사실 확인 (문제 있으면 올리지 않음)
uv run naver-blog-cli ai-draft --keywords 세종시,가을,산책 --search --verify --category 휴식
# 이미 있는 원고만 사실 확인
uv run naver-blog-cli verify-draft post.md --region 세종시

# 글+이미지가 한 폴더에 있을 때
uv run naver-blog-cli create-draft-from-folder ./내글폴더

# 발행/삭제는 되돌릴 수 없어서 --confirm 을 반드시 붙여야 합니다
uv run naver-blog-cli publish-draft --confirm --title "제목"
uv run naver-blog-cli delete-draft --confirm --title "제목"
uv run naver-blog-cli delete-post --confirm <글URL 또는 글번호>
```

`--help`로 각 명령의 전체 옵션을 볼 수 있습니다 (`uv run naver-blog-cli create-draft --help`).

### 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `NAVER_BLOG_ID` | (필수) | 블로그 아이디. `blog.naver.com/<여기>` |
| `NAVER_STATE` | `playwright-state/storage_state.json` | 쿠키 파일 경로. **절대경로 권장** |
| `HEADLESS` | `false` | `true`면 브라우저 창을 띄우지 않음 |
| `NAVER_COVER` | `images/00-cover.*` | 대표 이미지로 쓸 표지 파일. `0`/`off` 면 넣지 않음 |

| `NAVER_LLM_MODEL` | `qwen3.6:27b` | `ai-draft` 가 쓸 Ollama 모델 |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama 주소 |
| `NAVER_CLIENT_ID` | - | `--search`/`--verify` 용 네이버 검색 API(NAVER API HUB) Client ID |
| `NAVER_CLIENT_SECRET` | - | 같은 키의 Client Secret. **코드·저장소에 넣지 말고 환경변수로만** |

`HEADLESS` 기본값이 `false`인 건 의도입니다 — CAPTCHA가 뜨면 사람이 풀어야 하니까요.
`true`로 두면 그런 상황에서 조용히 실패합니다.

## 로컬 LLM으로 원고 만들기 (`ai-draft`)

> 추가: 송중호 (2026-10-03) — `src/naver_blog_cli/llm.py`, `cli.py` 의 `ai-draft`

자료 문장과 키워드를 주면 로컬 [Ollama](https://ollama.com) 모델이 마크다운 원고를 쓰고,
그 원고를 그대로 임시저장합니다. 외부 API·추가 패키지 없이 Ollama HTTP API만 씁니다.

```bash
ollama pull qwen3.6:27b        # 최초 1회 (약 17GB). latest 태그는 35B(24GB)라 :27b 지정

# 대화형: 자료 문장과 키워드를 차례로 물어봄 (자료 입력은 빈 줄에서 엔터 두 번으로 끝)
uv run naver-blog-cli ai-draft --category 휴식

# 자료를 파일로
uv run naver-blog-cli ai-draft --file 자료.md --keywords 세종시,추석연휴 --category 휴식 \
    --request "가족 나들이 위주로" --length 1500

# 원고만 만들고 올리지 않기 → drafts/ 에서 고친 뒤 create-draft 로 올림
uv run naver-blog-cli ai-draft --text "..." --keywords 세종시 --dry-run
uv run naver-blog-cli create-draft --file drafts/20261003-151816_제목.md --category 휴식
```

### 네이버 검색으로 자료 수집·사실 확인 (`--search`, `--verify`, `verify-draft`)

> 추가: 송중호 (2026-10-03) — `search.py`, `verify.py`

```bash
uv run naver-blog-cli ai-draft --keywords 세종시,가을,산책코스 --search --verify --region 세종시 --category 휴식
uv run naver-blog-cli verify-draft drafts/원고.md --region 세종시
```

- `--search`: 쓰기 전에 키워드로 네이버 뉴스·웹문서·블로그를 5건씩 검색해 자료로 넘깁니다.
  자료 없이 쓰면 장소를 지어내지만, 검색 결과를 자료로 주면 크게 줄어듭니다.
- `--verify`: 쓴 뒤 모델이 원고에서 장소와 사실 문장을 뽑고, 네이버 검색으로 확인해
  `drafts/…_확인.md` 보고서를 만듭니다. **문제(❌)가 하나라도 있으면 임시저장하지 않습니다**
  (`--upload-anyway` 로 무시). 원고를 자동으로 고치지는 않습니다.
  - 장소: 지역 검색 → 웹문서·블로그 순. ✅ 그 지역에 있음 / 🟡 웹·블로그 언급만 (산책로·다리 등)
    / ❌ 다른 지역에만 있음 / ❌ 어디에도 없음. 이 판정은 LLM 없이 검색 결과로만 합니다.
  - 사실: 뉴스·웹문서 검색 결과를 모델에게 보여주고 ✅ 근거 있음 / ⚠️ 확인 불가 / ❌ 다름 판정.
    같은 로컬 모델이 판단하므로 참고용입니다.
- 실측(2026-10-03): 자료 없이 쓴 원고의 지어낸 장소 4곳(`서수원호수공원`, `전의호수공원` 등)을 모두 ❌ 로 잡았습니다.

네이버 검색 API 는 2026년에 개발자센터(openapi.naver.com)에서 **NAVER API HUB**(네이버클라우드)로
옮겨졌습니다. 키는 네이버클라우드 콘솔 > AI·NAVER API > Application 에서 검색 API 를 골라 받습니다
(Client ID 10자, Secret 40자). 주소는 `https://naverapihub.apigw.ntruss.com/search/v1/…`, 헤더는
`X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` 입니다.

google.com 은 쓰지 않습니다. curl 로는 자바스크립트 요구 페이지만 오고, Playwright 로는 첫 요청부터
캡차(`/sorry/`)로 막혔습니다(2026-10-03 실측). 약관상 자동 수집도 금지입니다.

동작 순서:

1. 모델 호출 (`/api/chat`, `think: false`). 답을 받으면 바로 모델을 메모리에서 내림(`keep_alive: 0`) —
   이어서 브라우저를 띄우므로 32GB 맥에서 메모리를 비워두려는 것.
2. 코드펜스·`<think>` 제거, 끝의 해시태그 줄은 본문에서 떼어 태그로 돌림.
3. `drafts/날짜_제목.md` 로 저장 (`drafts/` 는 `.gitignore` 대상).
4. 키워드 + `--tags` + 모델이 붙인 해시태그를 합쳐 태그로, 첫 줄 `# 제목` 을 제목으로 임시저장.

주의:

- **로컬 모델은 사실을 지어냅니다.** 2026-10-03 실측에서 자료 없이 "세종시 산책 코스"를 시키자
  수원의 공원 이름을 썼습니다. 프롬프트가 "자료에 있는 사실만" 쓰도록 묶지만, 장소·날짜·요금은
  **자료로 직접 주고**, 발행 전에 꼭 확인하세요.
- 한자·일본어 글자가 섞이면(예: `번华中`, `あっ`) 그 문장만 모델에게 다시 쓰게 해 고칩니다.
  섞인 글자를 보여주면 모델이 그대로 따라 써서, 그 자리를 빈칸(＿＿)으로 바꿔 문맥으로 채우게 합니다.
  괄호 안 병기(`세종오식(世宗五食)`)는 건드리지 않습니다. 뜻이 조금 바뀔 수 있으니 확인하세요.
- M2 Max 32GB 실측: qwen3.6:27b 약 12 tok/s, 원고 한 편 1~2분, 최대 메모리 약 28GB.

## 명령 (core.py 의 함수, cli.py 가 그대로 호출)

| CLI 명령 | core.py 함수 | 설명 |
|---|---|---|
| `check-session` | `check_session()` | 세션이 살아있는지 확인 |
| `list-categories` | `list_categories()` | 카테고리 목록 (하위 카테고리는 들여쓰기) |
| `list-drafts` | `list_drafts()` | 임시저장 글 목록 |
| `create-draft` | `create_draft(title, markdown, category, tags)` | 글을 쓰고 **임시저장**. 발행하지 않음 |
| `publish-draft` | `publish_draft(confirm, title, visibility)` | 임시저장 글을 불러와 발행 |
| `delete-draft` | `delete_draft(confirm, title)` | 임시저장 글 삭제 |
| `delete-post` | `delete_post(url_or_log_no, confirm)` | 발행된 글 삭제 |

기본 흐름은 **임시저장 → 눈으로 확인 → 발행**입니다.

파괴적인 명령(`publish-draft`, `delete-draft`, `delete-post`)은 `--confirm`을 요구합니다.
앞의 둘은 대상이 애매하면(제목이 여러 글과 맞거나, 지정 없이 임시저장이 2건 이상)
거부하고 후보를 보여줍니다.

`visibility`는 `public` / `neighbor` / `both_neighbor` / `private` 중 하나입니다.

## 마크다운 지원 범위

전부 실제 에디터에 넣어보고 확인한 결과입니다.

| 문법 | 결과 |
|---|---|
| `# ## ###` 제목 | 글자 크기 24 / 19 / 15 |
| `**굵게**` `*기울임*` `~~취소선~~` | 지원 |
| `[텍스트](url)` | 문단·제목 안에서 지원 |
| `> 인용` | 인용구 컴포넌트 |
| `- 목록` / `1. 목록` | 순서/비순서 목록 |
| ` ```코드``` ` | 소스코드 컴포넌트 |
| `---` | 구분선 |
| GFM 파이프 표 | 표 컴포넌트 (셀 안 서식 유지) |
| `![캡션](로컬경로)` | 사진 + 캡션 |
| `:::file 로컬경로:::` | 파일 첨부 (개당 10MB) |
| `:::formula ...:::` | 수식 |
| `:::place 검색어:::` | 장소 (검색 결과 첫 번째) |
| `:::video 유튜브 주소:::` | 유튜브 영상 플레이어 (watch, youtu.be, shorts 주소만) |

이미지·파일은 **로컬 경로만** 됩니다 (URL 불가).

### 알려진 한계

- **인용문과 표 안의 링크는 사라집니다.** 링크를 넣으려면 타이핑 경로를 타야 하는데,
  타이핑으로는 인용구·표 컴포넌트 자체를 만들 수 없습니다. 블록 형태를 지키고 링크를 버립니다.
- **인라인 코드(`` `code` ``)는 지원하지 않습니다.** 네이버에 대응 기능이 없습니다.
- **장소는 검색 결과 중 첫 번째**를 씁니다. 정확히 지정하려면 검색어를 구체적으로 주세요
  (`:::place 강남역 2호선:::`). 어느 장소를 골랐는지는 결과에 표시됩니다.
- 수식에 언어·스타일 지정 수단은 없습니다.

## 셀렉터가 깨졌을 때

네이버가 에디터를 바꾸면 툴이 `"...을 못 찾음"`을 반환합니다. 진단 스크립트가 있습니다.

```bash
export NAVER_BLOG_ID=<블로그아이디>
uv run python verify_selectors.py            # 창 띄움
HEADLESS=true uv run python verify_selectors.py   # 창 없이
```

에디터 첫 화면과 발행 레이어를 2단계로 검사해 `OK` / `HIDDEN` / `MISS`를 출력합니다.
`MISS`가 있으면 `dom_probe.txt`(클릭·입력 가능한 요소 목록)와 `dom_dump.html`을 남기니,
그걸 보고 `selectors.py`만 고치면 됩니다.

**셀렉터 문자열은 전부 `src/naver_blog_cli/selectors.py` 한 파일에 있습니다.**
다른 파일에는 두지 마세요.

## 구조

```
src/naver_blog_cli/
  selectors.py   셀렉터 격리 구역. 네이버가 바뀌면 여기만 고친다
  ir.py          마크다운 → 블록 IR → HTML. 붙여넣기 가능/불가능 라우팅
  editor.py      에디터 구동부 (붙여넣기, 업로드, 툴바 조작)
  session.py     쿠키 로드/저장. 비밀번호는 다루지 않는다
  material.py    글감(뉴스·증권·책) 카드 고르기
  core.py        핵심 로직 (전송 방식과 무관, MCP 의존 없음)
  cli.py         터미널 진입점. core.py 를 그대로 호출
login_setup.py   최초 1회 사람이 직접 로그인
verify_selectors.py  셀렉터 진단
```

핵심 설계는 `CLAUDE.md`에 이유와 함께 적혀 있습니다. 특히:

- 본문은 **클립보드 HTML 붙여넣기**가 1차 경로입니다. 툴바 클릭보다 훨씬 안정적입니다.
- 붙여넣기가 뭉개는 것(목록·코드블록·링크)만 툴바·키보드로 따로 만듭니다.
- 이미지·파일·수식·장소는 붙여넣기가 불가능해 툴바를 거칩니다.

## 기여

셀렉터가 깨진 걸 발견하면 `verify_selectors.py` 출력과 함께 이슈를 남겨주세요.
`selectors.py`의 후보 리스트는 의미 기반(`data-click-area`, `data-testid`, `data-name`,
`aria-label`) → 클래스 접두 → 난독화 클래스 순서로 둡니다. 네이버의 난독화 클래스는
해시만 도는 경우가 많아 `class*=` 접두 매칭이 잘 견딥니다.

## 출처와 라이선스

이 프로젝트는 아래 저장소의 코드를 바탕으로 수정한 것입니다.

- **참고·기반 저장소: [Johnhyeon/naver-blog-mcp](https://github.com/Johnhyeon/naver-blog-mcp)**
  — Johnhyeon \<whdqja216772@gmail.com\> (기능 확장)
- 그 원본: [jjorae/naver-blog-mcp](https://github.com/jjorae/naver-blog-mcp)
  — jjorae \<raehyeok.cho@gmail.com\> (최초 작성)

원본은 [MIT 라이선스](LICENSE)이며, 이 저장소도 같은 MIT 라이선스로 배포합니다.
MIT 조건에 따라 원저작자의 저작권 표시와 허가 문구를 [LICENSE](LICENSE)에 그대로 유지했습니다.
원본의 git 커밋 기록도 지우지 않고 그대로 이어받았습니다.

이 저장소에서 바꾼 것(송중호, 2026-09-22): MCP 서버(`server.py`) 제거,
`core.py` + `cli.py` 구조의 CLI로 변경, 패키지명 `naver_blog_mcp` → `naver_blog_cli`.

## 이 포크에서 더한 것 (Johnhyeon)

- `create_draft_from_folder(folder)` — 글 파일과 이미지가 같은 폴더에 있을 때 폴더째 임시저장한다.
  이미지의 상대경로를 절대경로로 바꾸고, `meta.json` 의 제목·카테고리·태그를 읽고,
  글 첫 줄의 `# 제목` 을 제목으로 쓴다. **브라우저를 열기 전에** 이미지 파일을 모두 확인해서
  하나라도 없거나 10MB 를 넘으면 아무것도 하지 않고 목록으로 알려준다.
- `NAVER_BLOG_READONLY=1` — 발행·삭제 도구를 **도구 목록에서 아예 뺀다.** 임시저장까지만 돌리는 운영용.
- 카테고리를 `"종목 분석 > 국장"` 처럼 경로로 줘도 된다. 마지막 칸으로 고른다.
- `NAVER_KEEP_OPEN=1` — 일이 끝나도 브라우저 창을 닫지 않는다. 사람이 결과를 보고 창을 닫으면 그때 종료(기본 10분, 숫자를 주면 그 초만큼).
- `delete_draft`, `publish_draft` 에 `index` — 같은 제목으로 여러 번 임시저장했을 때 목록 순번(1이 최신)으로 고른다.
- **대표 이미지 자동 지정** — 글 폴더에 `images/00-cover.png` 가 있으면 본문 맨 앞에 넣고
  대표 이미지(검색 결과·블로그 목록 섬네일)로 지정한다. 네이버는 **본문에 들어간 이미지 중에서만**
  대표를 고르게 해서 따로 올리는 칸이 없다(2026-09-18 실측). 그래서 표지를 섬네일로 쓰려면
  본문 맨 앞에 두는 수밖에 없고, 그 자리는 독자에게도 보인다. 본문이 이미 그 파일을 쓰고 있으면
  두 번 넣지 않는다. 끄려면 `NAVER_COVER=0`.

## 글감 카드 (fork 추가, 2026-09-16)

마크다운 한 줄로 네이버 글감 카드를 넣는다.

```
:::news 머니투데이 | 한국첨단소재, ETRI와 광통신용 초고속 반도체 연결 기술 이전 계약:::
:::stock 072950:::
:::book 주식투자를 잘한다는 것 | 기본형:::
```

- 뉴스는 매체와 제목이 둘 다 맞아야 넣는다. 같은 제목을 다른 매체가 실은 경우가 흔하다
- 기본 모양은 요약형(제목 전체와 매체 한 줄). `| 기본형` 이면 썸네일 카드
- 쓰기 전에 전부 검색해 보고, 못 찾은 카드는 `매체, 제목` 글자로 바꿔 쓴다
- 증권 카드는 넣는 순간 시세를 굳힌다(애프터마켓 시간에는 정규장 종가와 다르다)
