# Tiny Second-hand Shopping Platform

Flask 기반의 소형 중고거래 플랫폼입니다. 회원가입, 상품 등록/조회, 검색, 전체 채팅, 1대1 채팅, 신고 기반 차단, 사용자 간 송금, 관리자 통합 관리 기능을 포함합니다.

## 핵심 기능

- 회원가입, 로그인, 로그아웃, 프로필 수정, 회원 탈퇴
- 상품 등록, 조회, 수정, 삭제, 내 상품 관리
- 상품 검색(상품명/설명/카테고리/판매자 기준)
- 전체 채팅 및 1대1 채팅
- 사용자 신고, 상품 신고, 신고 누적 기반 자동 차단/정지
- 사용자 간 송금 및 거래 메모 기록
- 관리자 대시보드, 사용자/상품/신고/메시지/송금 기록 관리

## 기술 스택

- Python 3.11+
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- Flask-SocketIO
- Flask-Limiter
- SQLite

## 프로젝트 구조
- Tiny-Second-hand-Shopping-Platform(V0)
  -> 보안 문제 해결 전 버전
- Tiny-Second-hand-Shopping-Platform
  -> 보안 문제 해결 후 버전
- Tiny-Second-hand-Shopping-Platform(V2)
  -> 유지보수 이후 버전(보안 문제 추가 해결, improved.md에 내용 존재)

## 로컬 실행 방법
0. 3개의 폴더 중 실행 시킬 버전의 폴더로 cd로 이동.

1. Python 가상환경 생성, 

```bash
python -m venv .venv
```

2. 가상환경 활성화

- Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

- Ubuntu / bash

```bash
source .venv/bin/activate
```

3. 의존성 설치

```bash
pip install -r requirements.txt
```

4. 환경 변수 설정

`.env.example`를 참고해서 값을 준비합니다.

필수 권장값:

- `SECRET_KEY`: 충분히 긴 랜덤 문자열
- `ADMIN_USERNAME`: 초기 관리자 아이디
- `ADMIN_PASSWORD`: 초기 관리자 비밀번호

예시:

```bash
export SECRET_KEY="replace-this-with-a-long-random-secret"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="ChangeMe123!"
```

Windows PowerShell 예시:

```powershell
$env:SECRET_KEY="replace-this-with-a-long-random-secret"
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="ChangeMe123!"
```

5. 서버 실행

```bash
python run.py
```

6. 브라우저 접속

```text
http://127.0.0.1:5000
```

## Ubuntu VM + ngrok 실행 방법

질문에서 언급한 VMware Ubuntu + ngrok 환경 기준 실행 절차입니다.

### 1) Ubuntu 패키지 설치

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2) 프로젝트 준비

GitHub에 public 저장소를 올린 뒤 Ubuntu VM에서 클론합니다.

```bash
git clone <YOUR_PUBLIC_GITHUB_REPOSITORY_URL>
cd tiny-second-hand-shopping-platform
```

### 3) 가상환경 및 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) 환경 변수 적용

```bash
cp .env.example .env
```

`.env`를 열어서 아래 항목은 꼭 수정하세요.

- `SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SESSION_COOKIE_SECURE`
- `PREFERRED_URL_SCHEME`
- `SOCKETIO_CORS_ALLOWED_ORIGINS`

ngrok을 사용할 때 권장 설정 예시:

```bash
export SECRET_KEY="replace-this-with-a-long-random-secret"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="StrongAdminPass123!"
export SESSION_COOKIE_SECURE=1
export PREFERRED_URL_SCHEME=https
export SOCKETIO_CORS_ALLOWED_ORIGINS="https://your-ngrok-domain.ngrok-free.app"
```

### 5) Flask 서버 실행

```bash
source .venv/bin/activate
python run.py
```

### 6) ngrok 연결

다른 터미널에서 ngrok 실행:

```bash
ngrok http 5000
```

생성된 `https://...ngrok-free.app` 주소로 접속합니다.

중요:

- ngrok 주소가 바뀌면 `SOCKETIO_CORS_ALLOWED_ORIGINS`도 새 주소로 맞춰야 채팅이 정상 동작합니다.
- HTTPS 터널을 사용할 때는 `SESSION_COOKIE_SECURE=1`이 권장됩니다.

## 기본 관리자 계정

앱이 처음 실행될 때 초기 관리자 계정이 자동 생성됩니다.

- 아이디: `ADMIN_USERNAME`
- 비밀번호: `ADMIN_PASSWORD`

반드시 공개 배포 전에 기본값을 변경하세요.

## 테스트 실행

```bash
python -m unittest discover -s tests
```

## 보안 관련 기본 설정

- 비밀번호 해시 저장
- CSRF 보호
- 이미지 확장자 및 실제 이미지 검증
- 로그인/회원가입/신고/상품 등록 속도 제한
- 채팅 도배 방지 메시지 윈도우 제한
- 신고 중복 접수 방지
- 관리자 권한 검사 및 IDOR 방지
- 안전한 `next` URL 검사
- SameSite/HttpOnly 쿠키 기본 적용 등등
