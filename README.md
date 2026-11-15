# Google TTS Desktop GUI

This project creates a desktop app for Google Cloud Text-to-Speech using PyQt6.

Features:
- Select a Google Cloud service account JSON file
- Choose a language and voice
- Enter text to synthesize
- Save generated audio to MP3
- Play the generated file from the app

Requirements:
1. A Google Cloud project with the Text-to-Speech API enabled
2. A service account JSON key with access to the API
3. Python 3.10+

Setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

How to create credentials:
1. Open the Google Cloud Console
2. Create or select a project
3. Enable the Text-to-Speech API
4. Create a service account
5. Download the JSON key
6. Select that file in the app

Note:
Google Cloud TTS is a paid service. This app does not provide free speech conversion.

---

# YouTube 다국어 일괄 업로더 (`youtube_uploader`)

롱폼 영상 1편을 언어별 버전(ko / en / ja / es …)으로 나눠 **언어마다 정해진 채널**에 한 번에 업로드하는 CLI 도구입니다.
대본(`script.txt`)으로 제목·설명·태그를 만들고, 썸네일과 자막(.srt)도 함께 올립니다.

## 1. 최초 설정 (한 번만)

1. Google Cloud Console에서 **YouTube Data API v3**를 사용 설정합니다.
2. **OAuth 동의 화면**을 만들고, 업로드할 채널의 Google 계정을 테스트 사용자로 추가합니다.
3. OAuth 클라이언트 ID를 **데스크톱 앱** 유형으로 만들고 JSON을 `secrets/client_secret.json`으로 저장합니다.
   (클라이언트 하나로 모든 채널을 처리하며, 채널마다 토큰만 따로 저장됩니다.)
4. 설치와 설정:

```bash
pip install -r requirements-uploader.txt
cp channels.example.json channels.json   # 채널 이름·언어·기본 공개 상태를 수정
python -m youtube_uploader auth ko       # 브라우저에서 '한국 채널'을 선택
python -m youtube_uploader auth en
python -m youtube_uploader auth ja
```

`auth`가 출력하는 `channel_id`를 `channels.json`에 넣어 두면, 업로드 전에 토큰의 채널이 맞는지 확인하고
다르면 업로드를 중단합니다(다른 나라 채널에 잘못 올라가는 것을 막습니다).

## 2. 영상마다

```bash
python -m youtube_uploader init jobs/paper_origin
```

```
jobs/paper_origin/
  ko/  video.mp4  script.txt  [thumbnail.jpg]  [ko.srt]
  en/  video.mp4  script.txt  [thumbnail.jpg]  [en.srt]
  ja/  video.mp4  script.txt  [thumbnail.jpg]  [ja.srt]
```

폴더 이름(ko/en/ja)은 `channels.json`의 채널 키와 같아야 합니다.

```bash
# 언어별 meta.json(제목/설명/태그) 생성
python -m youtube_uploader prepare jobs/paper_origin         # 대본 첫 줄 = 제목 (무료)
python -m youtube_uploader prepare jobs/paper_origin --ai    # Claude가 언어별로 작성 (ANTHROPIC_API_KEY 필요)

# meta.json 확인/수정 후
python -m youtube_uploader upload jobs/paper_origin --dry-run                         # 계획·쿼터만 확인
python -m youtube_uploader upload jobs/paper_origin --publish-at 2026-11-20T18:00:00+09:00
python -m youtube_uploader upload jobs/paper_origin --only en,ja
```

`meta.json` 필드: `title`, `description`, `tags`, 선택 `privacy`, `publish_at`, `category_id`,
`made_for_kids`, `contains_synthetic_media`. 언어마다 `publish_at`을 다르게 주면 나라별 시간대에 맞춰 예약 공개됩니다.

업로드가 끝나면 언어 폴더에 `upload_result.json`(영상 ID·URL)이 저장되고, 다시 실행해도 같은 영상을 두 번 올리지 않습니다
(`--force`로 강제 재업로드). 중간에 실패한 언어만 다시 실행하면 됩니다.

## 알아둘 점

- **쿼터**: 영상 업로드 1회 ≈ 1,600 단위, 썸네일 50, 자막 400. 기본 한도는 Google Cloud 프로젝트당 하루 10,000이라
  3개 채널 × 1편(≈5,000)은 충분하지만 하루 2편이 넘으면 한도 증설 신청이 필요합니다.
- **미검증 API 프로젝트**: Google 감사(audit)를 받지 않은 프로젝트로 올린 영상은 **비공개로 고정**됩니다.
  감사 전까지는 `private`로 올리고 YouTube Studio에서 공개로 바꾸거나, YouTube API 감사를 신청하세요.
- **앱이 '테스트 중' 상태면** 로그인이 7일마다 만료됩니다. `upload` 중 만료된 채널이 있으면 브라우저가 자동으로 열리니
  해당 채널을 다시 선택하면 그대로 이어서 업로드됩니다.
- **커스텀 썸네일**은 전화번호 인증된 채널에서만 됩니다(실패해도 영상 업로드는 유지됩니다).
- **AI 생성 콘텐츠 표시**: 사실처럼 보이는 AI 영상이면 `contains_synthetic_media: true`로 설정하세요.
- `channels.json`, `secrets/`, `tokens/`, `jobs/`는 `.gitignore`에 들어 있어 커밋되지 않습니다.
