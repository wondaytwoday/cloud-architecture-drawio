# Cloud Architecture draw.io Skill

AWS·Azure·GCP 아키텍처를 CSP 아이콘, 네트워크 박스, 통신선으로 표현하는 에이전트 스킬입니다.

- 스킬: [SKILL.md](cloud-architecture-drawio/SKILL.md)
- 예제와 미리보기: [examples/](examples/)
- 검증 결과: [evals/RESULTS.md](evals/RESULTS.md)
- 선 배치 규칙과 조사 근거: [routing.md](cloud-architecture-drawio/references/routing.md)

v2는 연결 지점 분산, 선 중첩 방지, 장애물 여백, 교차 점프 표시, 연결선에 붙는 라벨, CSP 경계 검사를 보강했습니다. 다섯 예제의 선 교차는 25 → 2, 중첩 길이는 236 → 0 px로 줄었고 회귀 테스트 43개를 통과했습니다. 라우터와 예제 배치 개선을 함께 반영한 수치입니다.

미리보기: [AWS 한글](examples/aws-three-tier-ko.png) · [AWS 3 AZ](examples/aws-three-az.png) · [Azure](examples/azure-regional.png) · [GCP](examples/gcp-regional.png)

## 설치

저장소를 복제하거나 [스킬 배포 ZIP](dist/cloud-architecture-drawio-v2.zip)을 받아 압축을 푸세요. **`cloud-architecture-drawio/` 폴더 전체를 복사해야 합니다.** `SKILL.md`에서 `scripts/`, `references/`, `assets/`를 사용하므로 파일 하나만 옮기면 동작하지 않습니다.

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

## 범위

검수한 템플릿을 수정하는 방식이며, 모든 토폴로지를 자동 배치하는 엔진은 아닙니다. 사용자 입력을 모델로 해석하고 좌표·경계를 선택하는 작업은 에이전트가 수행합니다. 생성기는 네이티브 draw.io 파일, 내장 벡터 아이콘, 직각 라우팅, 일부 구조·도메인 검사를 담당합니다. 실제 라우팅·보안 정책의 도달 가능성을 증명하지는 않습니다.
