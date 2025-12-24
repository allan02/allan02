# 풋살 예약 자동화(안전 템플릿) - futsalbase.com

이 폴더는 `https://www.futsalbase.com`용 **브라우저 자동화 템플릿**입니다.

중요: 예약 사이트는 약관/정책에 따라 자동화가 제한될 수 있습니다.  
그래서 기본값은 **결제/최종확정 버튼은 누르지 않고(=DRY RUN) 직전에서 멈추도록** 되어 있습니다.

## 구성

- `reserve.py`: 로그인 → 예약 페이지 이동 → 시간 슬롯 선택까지(템플릿)
- `config.futsalbase.example.json`: 사이트/선택자/희망 일정 설정 예시
- `.env.example`: 계정/옵션 환경변수 예시
- `artifacts/`: 스크린샷/트레이스 저장 폴더(자동 생성)

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r macro/requirements.txt
python -m playwright install chromium
```

## 설정

### 1) 계정 정보

```bash
cp macro/.env.example macro/.env
```

`macro/.env`에 아래 값을 채우세요.

- `FUTSAL_USERNAME`
- `FUTSAL_PASSWORD`

옵션:

- `HEADLESS=1` (기본) / `0` (브라우저를 띄워서 보기)
- `SLOW_MO_MS=0` (동작을 천천히 보고 싶으면 200~800 추천)
- `TRACE=0` (문제 생기면 1로 켜서 `artifacts/trace*.zip` 확보)

### 2) 사이트 선택자(Selectors) 채우기

`config.futsalbase.example.json`은 **플레이스홀더**입니다.  
futsalbase는 화면/클래스명이 바뀔 수 있으니, 아래 방법으로 선택자를 “녹화”해서 채우는 걸 권장합니다.

#### 추천: Playwright codegen으로 녹화

로컬에서 아래를 실행하면 클릭/입력 동작에 맞는 선택자가 자동으로 생성됩니다.

```bash
python -m playwright codegen "https://www.futsalbase.com/home"
```

녹화된 코드에서 아래 항목에 해당하는 선택자를 찾아
`config.futsalbase.example.json`의 `selectors` / `reservation.selectors`에 복사하세요.

- 로그인: `username`, `password`, `submit`
- 로그인 성공 확인: `post_login_marker` (예: “로그아웃” 텍스트)
- 예약 화면 이동: `go_to_schedule`
- 구장/날짜/시간 선택 및 예약 버튼 등

## 실행 (기본: DRY RUN)

아래는 **최종 확정/결제 클릭 없이** 예약 직전까지 진행합니다.

```bash
python macro/reserve.py --config macro/config.futsalbase.example.json
```

실패하면 `macro/artifacts/screenshots/`에 스크린샷이 저장됩니다.

## (선택) 최종 확정 클릭

정말 필요할 때만, 설정에서 `dry_run=false`로 바꾸고 `--confirm`를 함께 사용하세요.

```bash
python macro/reserve.py --config macro/config.futsalbase.example.json --confirm
```

## 오픈 시간 대기

`config`의 `reservation.open_at`에 ISO 8601 시간을 넣으면 그 시각까지 대기 후 실행합니다.

예:

- `"2025-12-31T10:00:00+09:00"`
- `"2025-12-31T01:00:00Z"`

