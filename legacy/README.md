# legacy/ — 보관 파일 (실행에 쓰이지 않음)

2026-11-26 저장소 정리에서 루트와 `scripts/`에 남아 있던 개발용 파일을 여기로 옮겼습니다.
지우지 않고 보관만 했으니, 필요하면 그대로 참고하거나 되돌릴 수 있습니다.

| 파일 | 원래 위치 | 무엇이었나 | 왜 내렸나 |
|---|---|---|---|
| `ICAN_Dashboard.html` | `/` | 뉴스 미리보기 + 디자인 스펙을 나란히 보는 개발용 분할 화면 (iframe) | 어떤 페이지·스크립트도 링크하지 않음 |
| `ican_design_spec.md` | `/` | 위 대시보드가 읽던 디자인 스펙 메모 | 대시보드와 함께만 쓰임 |
| `debug_academy.py` | `/` | 아카데미 데이터 디버깅용 임시 스크립트 | 워크플로·생성 스크립트에서 호출하지 않음 |
| `template.html` | `scripts/` | `<!--SLOT:...-->` 마커 기반의 옛 HTML 템플릿 | 현재 발행은 `scripts/inject-direct.py`가 HTML 전체를 생성 |
| `inject-content.py` | `scripts/` | 슬롯 마커를 채우던 옛 주입기 | `inject-direct.py`로 대체됨 |

## 그대로 둔 파일

- `food-hunter-ortigas.html` + `css/food-hunter.css` — 앱 화면에서는 링크되지 않지만
  독립된 공개 페이지(MANILA FOOD HUNTER VOL. 01)이고 `sw.js`가 CSS를 프리캐시합니다.
  주소를 공유한 적이 있다면 404가 되므로 옮기지 않았습니다.
- `scripts/update-herald.sh` — 특정 날짜 에디션을 수동으로 다시 만드는 복구용 스크립트.
  자동 발행에는 쓰이지 않지만 사람이 직접 실행하는 용도로 남겼습니다.

## 현재 발행 경로 (참고)

`.github/workflows/daily-publish.yml`
→ `scripts/generate-daily.sh`
→ (`scripts/fetch-news.py` RSS 수집, `scripts/fetch-live-data.py` 환율·날씨 덮어쓰기)
→ `scripts/inject-direct.py` → `ican_news.html` / `index.html`
