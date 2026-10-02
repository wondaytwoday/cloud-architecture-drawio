# Cloud Architecture draw.io Skill

AWS·Azure·GCP 아키텍처를 CSP 아이콘, 네트워크 박스, 통신선으로 표현하는 에이전트 스킬입니다.

- 스킬: [SKILL.md](cloud-architecture-drawio/SKILL.md)
- 예제와 미리보기: [examples/](examples/)
- 검증 결과: [evals/RESULTS.md](evals/RESULTS.md)
- 선 배치 규칙과 조사 근거: [routing.md](cloud-architecture-drawio/references/routing.md)

v3는 "검사를 통과하면 올바른 그림"이라는 약속을 지키도록 검증을 강화했습니다.

- **검증기**
  - 그려진 위치와 선언한 `parent`가 다르면 거부합니다.
  - 컨테이너끼리 테두리가 교차하거나 노드가 경계에 걸치면 거부합니다.
  - 제목·범례 여백 침범, 오타 키(`parnet` 등), XML이 저장할 수 없는 문자를 거부합니다.
  - CSP 배치 규칙을 늘렸습니다. WAF·Shield·Cloud Armor, IGW·Cloud Router/NAT, App Gateway 전용 서브넷 규칙을 검사하고, multi 모드에서도 provider 규칙이 적용됩니다.
- **렌더러**
  - 잘린 텍스트, 점프 아크가 없는 교차, 편집 후 낡은 리포트, 리포트 누락을 실패로 처리합니다.
- **생성기**
  - draw.io에서 수동 편집한 파일을 재빌드가 덮어쓰지 못하게 막습니다.
  - 범례를 현지화합니다(`locale: "ko"`).
  - 한국어 Windows 같은 비 UTF-8 로캘에서도 동작합니다.

- **라우터**
  - 아직 그리지 않은 연결선의 리드인을 미리 예약하고, 컨테이너 테두리에 붙어 달리지 않습니다.
  - 라벨이 들어가지 않으면 평행선을 벌리는 방식 등 단순한 방식으로 차례로 다시 시도합니다.
  - 고정 코퍼스 841개 모델 기준으로 빌드 성공이 547 → 785개로 늘었고, 경로 실패는 210 → 0개입니다. 기존에 되던 모델이 실패하는 경우는 없습니다.
  - 캡션은 자기 선분 안쪽, 다른 선과 떨어진 자리를 먼저 고릅니다. 튀어나온 캡션은 78 → 12개, 다른 선에 붙은 캡션은 43 → 5개로 줄었습니다.
  - AWS 3-AZ 예제의 교차는 2 → 0입니다.
- **진단과 실행**
  - 빌드가 실패하면 들어가지 않는 라벨을 모두, 막는 도형 이름과 필요한 간격과 함께 보여 줍니다.
  - `check` 명령 하나로 검증·빌드·렌더 판정까지 끝냅니다.

v3의 마지막 단계에서는 그릴 수 있는 범위와 편집 흐름을 넓혔습니다.

- **아이콘**
  - 36개에서 93개로 늘렸습니다. AWS 데이터·메시징·컨테이너·보안·하이브리드 네트워크, Azure AKS·Functions·Cosmos DB·Firewall·Bastion, GCP GKE·Pub/Sub·BigQuery, CSP 중립 `generic.*` 도형을 포함합니다.
  - `scripts/add_icon.py`가 고정한 draw.io 커밋의 aws4·gcp2·networks·azure2 라이브러리를 검색해 아이콘을 추가하고, 출처와 SHA-256을 남깁니다. 기존 36개는 이 도구로 바이트 단위까지 똑같이 재현됩니다.
  - 서브넷 안에 있어야 하는지 같은 배치 규칙은 카탈로그의 `placement` 필드에 둡니다. 아이콘이 없어 일반 상자로 그린 자원은 `fallbackIcons`에 나옵니다.
- **배치 단축 표기**: 카드 크기 생략, `col`/`row` 격자, 자식을 감싸는 `"fit"` 박스, `"match:ID"`, `auto` 캔버스를 씁니다. 좌표를 손으로 계산하지 않아도 됩니다. `normalize`로 절대 좌표를 확인합니다.
- **템플릿**
  - 7개를 추가해 10개가 됐습니다: 서버리스, NAT egress, 멀티 리전 DR, EKS, 하이브리드 VPN과 Transit Gateway, Azure hub-spoke, GCP Cloud Run.
  - 모두 경고·교차 없이 빌드되고 렌더 검사를 통과합니다.
- **경계 연결**
  - VPC·VNet·서브넷·리전 경계끼리 선을 이을 수 있어 피어링·TGW 연결·VPN을 그대로 그립니다.
  - 관계 종류에 비동기 메시지 `event`와 네트워크 링크 `connectivity`를 추가했습니다.
  - 두 선이 한 직선 위에서 24px 이내로 맞닿아 한 선처럼 보이면 감지하고, 피해서 다시 라우팅합니다. 벤치마크에서 이런 맞닿음(10px 미만 어긋남 포함)이 995 → 254개로 줄었고, 새로 실패한 모델은 없습니다.
- **편집 흐름**
  - `pull`: draw.io에서 옮기거나 크기·소속·연결 끝·텍스트를 바꾼 내용을 모델로 되가져옵니다. 다시 빌드하면 그린 자리 그대로 나오는지 확인하고, 단축 표기로 재현할 수 없으면 그린 좌표로 바꿉니다. 손으로 추가한 도형이나 옮기지 못한 편집은 따로 알려 줍니다. `--embed`로 만든 PNG·SVG도 읽습니다.
  - `bundle`: 여러 모델을 한 `.drawio`의 여러 페이지로 묶습니다.
  - `render.cjs --embed`: PNG·SVG 미리보기 안에 원본을 넣어 draw.io에서 바로 편집할 수 있게 합니다.

회귀 테스트는 144개입니다(렌더 환경이 없으면 13개, draw.io 아이콘 라이브러리 캐시도 없으면 15개를 건너뜁니다). 3단계 변경분은 독립 에이전트 검토에서 재현된 30건을 모두 고쳤습니다([검증 결과](evals/RESULTS.md)). 라우팅 벤치마크는 `python3 evals/bench_routing.py`로 재현합니다.

v2는 연결 지점 분산, 선 중첩 방지, 장애물 여백, 교차 점프 표시, 연결선에 붙는 라벨, CSP 경계 검사를 보강했습니다. 다섯 예제의 선 교차는 25 → 2, 중첩 길이는 236 → 0 px로 줄었습니다. 라우터와 예제 배치 개선을 함께 반영한 수치입니다.

미리보기: [AWS 한글](examples/aws-three-tier-ko.png) · [AWS 3 AZ](examples/aws-three-az.png) · [Azure](examples/azure-regional.png) · [GCP](examples/gcp-regional.png) · [서버리스](examples/aws-serverless.png) · [NAT egress](examples/aws-egress.png) · [멀티 리전 DR](examples/aws-multi-region-dr.png) · [EKS](examples/aws-eks.png) · [하이브리드 VPN](examples/aws-hybrid-vpn.png) · [Azure hub-spoke](examples/azure-hub-spoke.png) · [GCP Cloud Run](examples/gcp-cloud-run.png)

## 설치

저장소를 복제하거나 [스킬 배포 ZIP](dist/cloud-architecture-drawio.zip)을 받아 압축을 푸세요. **`cloud-architecture-drawio/` 폴더 전체를 복사해야 합니다.** `SKILL.md`에서 `scripts/`, `references/`, `assets/`를 사용하므로 파일 하나만 옮기면 동작하지 않습니다.

| 에이전트 | 개인용 설치 위치 | 특정 프로젝트에만 설치 |
|---|---|---|
| [Claude Code](https://code.claude.com/docs/en/skills) | `~/.claude/skills/cloud-architecture-drawio/` | `<프로젝트>/.claude/skills/cloud-architecture-drawio/` |
| [Cursor](https://cursor.com/docs/skills) | `~/.cursor/skills/cloud-architecture-drawio/` | `<프로젝트>/.cursor/skills/cloud-architecture-drawio/` |

저장소 루트에서 Claude Code 개인용으로 설치하는 예시입니다.

```sh
mkdir -p ~/.claude/skills
cp -R cloud-architecture-drawio ~/.claude/skills/
```

Cursor에서는 위 명령의 `~/.claude/skills`를 `~/.cursor/skills`로 바꾸면 됩니다. 다른 에이전트에서도 스킬 폴더를 지정하거나 `cloud-architecture-drawio/SKILL.md`를 읽고 따르도록 요청할 수 있습니다.

실행 환경은 별도로 준비합니다.

- 편집 가능한 `.drawio` 생성: **Python 3**, 표준 라이브러리만 사용
- PNG·SVG 렌더링 및 검증: **draw.io Desktop**, 또는 **Node.js + Playwright + Chromium + draw.io viewer**

설치·실행 명령은 [렌더링 절차](cloud-architecture-drawio/references/rendering.md)를 참고하세요.

## 사용

예시 요청:

> $cloud-architecture-drawio AWS 2개 AZ에 public/private subnet을 나누고, ALB → EC2 웹 계층 → 내부 ALB → 앱 계층 → RDS primary/standby를 그려줘. 네트워크 경계와 통신 방향을 표시하고 drawio 원본과 PNG를 만들어줘.

Claude Code에서는 `/cloud-architecture-drawio`로 호출합니다. Azure와 GCP도 같은 방식으로 CSP와 필요한 구성을 지정하면 됩니다.

기존 모델을 직접 빌드할 때:

```sh
python3 cloud-architecture-drawio/scripts/cloud_drawio.py build \
  cloud-architecture-drawio/assets/templates/aws-three-tier.json \
  examples/aws-three-tier.drawio
python3 -m unittest discover -s evals -v
```

렌더 환경까지 갖췄다면 `check`가 검증·빌드·렌더 검사를 한 번에 합니다. 종료 코드는 성공 0, 실패 1, 렌더 불가 2입니다.

```sh
python3 cloud-architecture-drawio/scripts/cloud_drawio.py check \
  cloud-architecture-drawio/assets/templates/aws-three-tier.json \
  examples/aws-three-tier.drawio
```

draw.io에서 직접 고친 그림은 `pull`로 모델에 되가져온 뒤 다시 빌드합니다. 요약의 `unmodelled`·`missing`·`ignored`가 비어 있지 않으면 모델로 옮기지 못한 편집이 있다는 뜻이므로 먼저 모델에 반영하세요. 여러 페이지 파일은 페이지마다 `--page N`으로 가져온 뒤 `bundle ... --force`로 함께 다시 만듭니다.

```sh
python3 cloud-architecture-drawio/scripts/cloud_drawio.py pull \
  examples/aws-three-tier.drawio examples/aws-three-tier.model.json --output pulled.json
python3 cloud-architecture-drawio/scripts/cloud_drawio.py bundle views.drawio a.json b.json
NODE_PATH=<playwright>/node_modules node cloud-architecture-drawio/scripts/render.cjs \
  views.drawio views.drawio.png <viewer-static.min.js> --page 2 --embed
```

`build`는 draw.io에서 수정된 출력 파일을 덮어쓰지 않고 멈춥니다. 수정 내용을 버리려면 `--force`를 붙입니다. v3 이전에 만든 출력은 리포트에 파일 해시가 없어 이 보호를 받지 못합니다. 스킬 폴더를 바꾼 뒤에는 `python3 tools/build_dist.py`로 배포 ZIP을 다시 만드세요. ZIP과 폴더가 다르면 테스트가 실패합니다.

## 범위

검수한 템플릿을 수정하는 방식이며, 모든 토폴로지를 자동 배치하는 엔진은 아닙니다. 사용자 입력을 모델로 해석하고 좌표·경계를 선택하는 작업은 에이전트가 수행합니다. 생성기는 네이티브 draw.io 파일, 내장 벡터 아이콘, 직각 라우팅, 일부 구조·도메인 검사를 담당합니다. 실제 라우팅·보안 정책의 도달 가능성을 증명하지는 않습니다.
