# 검증 결과

검증일: 2026-10-08 (한국 시간)

최종 파일: `dist/YouTubeDownloader.exe` — 183,810,721 bytes (175.3 MiB)

SHA-256:

```text
626f158ead11cbe059dc92feef303cf05b24c94ec8dd9d2adde1ef2a0c8861f6
```

## 다운로드 내역 추가 후 통과한 검사

- 자동 테스트 15개: 기존 다운로드 동작, UI 단계와 작업 스레드 연결, 내역 저장 후 재조회, 부분 실패·중지·재시도 결과, 여러 저장소 인스턴스, 손상된 DB 보존, 누락된 결과 표시, 내역 저장 실패 시 다운로드 지속.
- 내역 창을 닫았다 다시 열어도 같은 기록이 표시되고 다운로드 단계가 유지됨을 확인.
- 내역 화면의 재생목록·영상별 결과, 링크와 저장 경로 표시를 실제 Windows 화면으로 확인.
- 내역 검사는 임시 DB를 사용하여 사용자 계정의 실제 내역에 테스트 기록을 남기지 않음.

## 초기 구현에서 통과한 다운로드 검사

- UI 네 단계 생성과 최소 창 크기에서 하단 조작 버튼 표시 확인.
- 내장 Node.js 실행, PO Token 서버 HTTP 응답, 플러그인 등록, 내장 EJS 파일 확인.
- 내장 FFmpeg로 합성 MKV 생성 후 FFprobe로 영상·음성 스트림 확인.
- 공개 테스트 재생목록에서 제목과 영상 목록 조회.
- 짧은 공개 영상 실제 다운로드, MKV 저장, WAV와 무음 MP4 별도 저장.
- 재다운로드 시 기존 파일을 보존하고 영상 ID를 붙인 새 파일 저장.
- 작업 완료 후 앱이 시작한 PO Token 서버 프로세스 종료 확인.

초기 구현의 실제 YouTube 다운로드 보고서: `.build-cache/portable check 한글/final-report.json`

## 최종 EXE 검사

EXE만 `.build-cache/history-portable 한글` 폴더로 복사한 뒤 해당 폴더에서 실행했습니다.
PATH는 Windows 시스템 폴더만 남겼으며 PYTHONHOME, PYTHONPATH, VIRTUAL_ENV를 제거했습니다.
최종 EXE의 자체 검사는 종료 코드 0, `ok: true`로 완료되었습니다.

최종 EXE에서 UI, SQLite 기록 저장·재조회와 내역 창, 내장 Node·PO Token 서버·플러그인·EJS,
FFmpeg·FFprobe 및 서버 종료를 검사했습니다. 이 기능 확장에서는 실제 YouTube 다운로드를 다시 실행하지 않았습니다.

상세 보고서: `.build-cache/history-portable 한글/report.json`

## 범위

별도의 초기 상태 Windows PC 또는 가상 머신에서는 검사하지 않았습니다.
공개된 짧은 영상과 작은 재생목록으로 검증했으며, 로그인·지역 제한 영상과 대규모 재생목록의 장시간 실행은 검사하지 않았습니다.
