# Tiny Second-hand Shopping Platform V2 개선 및 보안 강화 내역

## 1. 작업 목표

- 기존에 정리했던 취약점 외 추가적인 웹 보안 약점 점검 및 보완
- 관리자 검색/필터 기능 강화
- 채팅 읽음 처리, 상품 찜 기능 추가
- XSS 방어를 더 강하게 적용

## 2. 이번에 추가로 확인한 보안 이슈

### 2-1. 로그아웃 CSRF 가능성

문제:

- 기존 로그아웃이 `GET /auth/logout`으로 동작해서, 사용자가 악성 페이지를 열었을 때 의도치 않게 로그아웃될 수 있었다.

간단 PoC:

```html
<img src="http://127.0.0.1:5000/auth/logout">
```

패치 방법:

- `app/routes/auth.py`에서 로그아웃 라우트를 `POST` 전용으로 변경
- `app/templates/base.html`의 상단 로그아웃을 CSRF 토큰이 포함된 `<form method="post">`로 교체

결과:

- `GET /auth/logout`은 더 이상 동작하지 않고 `405 Method Not Allowed`가 반환된다.
- 정상 로그아웃은 CSRF 보호가 적용된 `POST` 요청으로만 가능하다.

관련 코드:

- `app/routes/auth.py`
- `app/templates/base.html`
- `tests/test_app.py`의 `test_logout_requires_post_and_post_logout_succeeds`

### 2-2. 보안 응답 헤더 부재

문제:

- 기존에는 클릭재킹, MIME sniffing, 과도한 리소스 로딩을 줄이기 위한 보안 헤더가 없었다.

간단 PoC:

- 브라우저 개발자도구의 Network 탭에서 응답 헤더 확인 시 `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` 등이 없었다.
- 외부 페이지에서 `<iframe src="...">` 형태로 서비스 페이지를 감쌀 수 있었다.

패치 방법:

- `app/__init__.py`의 `after_request`에서 아래 헤더를 일괄 추가
  - `Content-Security-Policy`
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy`
  - `Cross-Origin-Opener-Policy: same-origin`

결과:

- 기본적인 클릭재킹과 콘텐츠 스니핑 위험이 줄었고, 스크립트/스타일/연결 출처도 더 엄격하게 제한된다.

관련 코드:

- `app/__init__.py`
- `tests/test_app.py`의 `test_security_headers_present`

### 2-3. XSS 방어 추가 강화

문제:

- 기존에도 `bleach`와 Jinja 이스케이프가 있었지만, 방어 심도를 더 높일 여지가 있었다.

간단 PoC:

```html
<script>alert(1)</script>
```

패치 방법:

- `app/utils.py`의 `sanitize_text()`에서
  - 유니코드 정규화(`NFKC`)
  - 제어문자 제거
  - `strip_comments=True`
  - 기존 태그 제거 정책 유지
- `app/__init__.py`에서 CSP를 추가해 인라인/비허용 스크립트 실행을 한 번 더 차단

결과:

- 저장 전에 스크립트 태그/이벤트용 입력이 더 강하게 정리된다.
- 설령 미래에 일부 출력 실수가 생겨도 CSP가 추가 방어선 역할을 한다.

관련 코드:

- `app/utils.py`
- `app/__init__.py`
- `tests/test_app.py`의 `test_xss_payload_is_stripped_on_product_detail`

### 2-4. 세션 고정(Session Fixation) 완화

문제:

- 로그인 직전 세션 상태를 그대로 유지하면 세션 고정 공격면을 넓힐 수 있다.

패치 방법:

- `app/routes/auth.py`의 로그인 성공 직전에 `session.clear()`를 호출해 새 로그인 세션을 깨끗하게 시작하도록 했다.

결과:

- 로그인 시점의 세션 상태가 더 안전하게 초기화된다.

관련 코드:

- `app/routes/auth.py`

## 3. 점검했지만 직접 취약점 경로를 확인하지 못한 항목

다음 항목은 코드 기준으로 점검했지만, 현재 구조에서 직접적인 exploitable sink는 확인되지 않았다.

- SQL Injection: SQLAlchemy ORM 기반 조회/필터 위주라 직접 문자열 SQL 조립이 없었음
- Command Injection: `subprocess`, `os.system`, 외부 명령 실행 코드 없음
- LFI / RFI: 사용자 입력을 파일 경로로 받아 include/open 하는 라우트 없음
- SSTI: `render_template_string` 같은 동적 템플릿 렌더링 경로 없음

즉, 이 항목들은 “취약한 코드가 있어서 막았다”기보다는 “현재 구조상 직접 취약점 경로가 없음을 확인”한 상태다.

## 4. 관리자 검색/필터 기능 강화

기존 관리자 화면은 단순 목록 조회에 가까워 운영 효율이 낮았다. 다음과 같이 확장했다.

### 4-1. 사용자 관리

- 검색어: 아이디, 표시 이름, 소개글
- 상태 필터: 전체 / 활성 / 정지 / 탈퇴
- 권한 필터: 전체 / 관리자 / 일반
- 정렬: 최신 가입순 / 오래된 가입순 / 이름순 / 잔액 높은 순 / 잔액 낮은 순

관련 코드:

- `app/routes/admin.py`
- `app/templates/admin/users.html`

### 4-2. 상품 관리

- 검색어: 상품명, 설명, 카테고리, 판매자
- 판매 상태 필터: 판매중 / 예약중 / 판매완료
- 운영 상태 필터: 정상 / 차단 / 삭제 / 차단·삭제 포함
- 정렬: 최신 등록순 / 오래된 등록순 / 가격 높은 순 / 가격 낮은 순
- 상품별 찜 수 표시

관련 코드:

- `app/routes/admin.py`
- `app/templates/admin/products.html`

### 4-3. 신고 관리

- 검색어: 신고 사유, 신고자, 대상 사용자/상품
- 대상 유형 필터: 사용자 / 상품
- 상태 필터: 열림 / 해결
- 정렬: 최신 신고순 / 오래된 신고순

관련 코드:

- `app/routes/admin.py`
- `app/templates/admin/reports.html`

### 4-4. 메시지 관리

- 검색어: 메시지 내용, 발신자, 수신자
- 유형 필터: 전체 채팅 / 1대1 채팅
- 노출 상태 필터: 표시중 / 숨김
- 읽음 상태 필터: 전체 / 읽지 않음 / 읽음

관련 코드:

- `app/routes/admin.py`
- `app/templates/admin/messages.html`

### 4-5. 송금 기록

- 검색어: 송금자, 수신자, 메모
- 최소/최대 금액 필터
- 정렬: 최신순 / 오래된 순 / 금액 높은 순 / 금액 낮은 순

관련 코드:

- `app/routes/admin.py`
- `app/templates/admin/transactions.html`

## 5. 부가 기능 확장

### 5-1. 채팅 읽음 처리

추가 내용:

- 1대1 메시지에 `is_read`, `read_at` 필드 추가
- 채팅방 진입 시 읽지 않은 메시지를 자동 읽음 처리
- 소켓 이벤트로 읽음 상태를 실시간 반영
- 채팅 허브에서 미확인 메시지 수 표시

관련 코드:

- `app/models.py`
- `app/utils.py`
- `app/routes/chat.py`
- `app/socketio_events.py`
- `app/templates/chat/hub.html`
- `app/templates/chat/direct.html`
- `app/static/js/chat.js`

검증:

- `tests/test_app.py`의 `test_direct_chat_marks_messages_as_read`

### 5-2. 상품 찜 기능

추가 내용:

- `ProductFavorite` 테이블 추가
- 상품 목록/상세/사용자 프로필에서 찜하기/해제 가능
- `/products/favorites`에서 내 찜 목록 조회 가능
- 상품 목록 정렬에 `찜 많은 순` 추가
- 상단 네비게이션에 찜 개수 표시

관련 코드:

- `app/models.py`
- `app/utils.py`
- `app/routes/products.py`
- `app/routes/main.py`
- `app/templates/base.html`
- `app/templates/index.html`
- `app/templates/products/list.html`
- `app/templates/products/detail.html`
- `app/templates/profile/user_detail.html`

검증:

- `tests/test_app.py`의 `test_product_favorite_toggle_and_listing`

## 6. 적용 결과 요약

- 로그아웃 CSRF 완화: `GET` 로그아웃 제거, `POST` + CSRF 토큰 적용
- 보안 헤더 강화: CSP, 클릭재킹 방어, nosniff, referrer 정책 추가
- XSS 방어 심화: 입력 정규화/제어문자 제거/CSP 추가
- 세션 고정 완화: 로그인 시 세션 초기화
- 관리자 운영 효율 개선: 다중 검색/필터/정렬 지원
- 사용자 기능 확장: 읽음 처리, 찜 목록 기능 추가

## 7. 테스트 결과

실행 명령:

```bash
python -m unittest discover -s tests
```

결과:

- 총 11개 테스트 통과

포함된 핵심 검증 항목:

- 기본 상품 등록/검색
- 저장형 XSS 필터링
- 신고 누적 시 자동 차단
- 송금 무결성
- 관리자 대시보드 접근
- 회원 탈퇴 처리
- 상품 찜 추가/해제
- 1대1 채팅 읽음 처리
- 관리자 정지 계정 필터
- 로그아웃 POST 강제
- 보안 헤더 적용 확인
