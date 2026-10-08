# 검증 결과

검증일: 2026-10-08 (한국 시간)

최종 파일: `dist/YouTubeDownloader.exe` — 183,796,273 bytes (175.3 MiB)

SHA-256:

```text
d588cbb6c91b6206e5331f2d94bebe05bfe173f8fd9b1397cd65d803da71dc8e
```

## 통과한 검사

- 자동 테스트 7개: URL·모드 검증, Windows 파일명, 기존 파일 보존, 오류 재시도 순서, 비공개 영상 실패 처리, 중지, UI 단계와 작업 스레드 연결.
- UI 네 단계 생성과 최소 창 크기에서 하단 조작 버튼 표시 확인.
- 내장 Node.js 실행, PO Token 서버 HTTP 응답, 플러그인 등록, 내장 EJS 파일 확인.
- 내장 FFmpeg로 합성 MKV 생성 후 FFprobe로 영상·음성 스트림 확인.
- 공개 테스트 재생목록에서 제목과 영상 목록 조회.
- 짧은 공개 영상 실제 다운로드, MKV 저장, WAV와 무음 MP4 별도 저장.
- 재다운로드 시 기존 파일을 보존하고 영상 ID를 붙인 새 파일 저장.
- 작업 완료 후 앱이 시작한 PO Token 서버 프로세스 종료 확인.

EXE만 `.build-cache/portable check 한글` 폴더로 복사한 뒤 해당 폴더에서 실행했습니다.
PATH는 Windows 시스템 폴더만 남겼으며 PYTHONHOME, PYTHONPATH, VIRTUAL_ENV를 제거했습니다.
최종 EXE의 자체 검사는 종료 코드 0, `ok: true`로 완료되었습니다.

상세 보고서: `.build-cache/portable check 한글/final-report.json`

## 범위

별도의 초기 상태 Windows PC 또는 가상 머신에서는 검사하지 않았습니다.
공개된 짧은 영상과 작은 재생목록으로 검증했으며, 로그인·지역 제한 영상과 대규모 재생목록의 장시간 실행은 검사하지 않았습니다.
