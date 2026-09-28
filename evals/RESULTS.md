# 검증 결과 — v2, 2026-09-28

AWS·Azure·GCP 예제에 스킬을 적용하고 실제 draw.io viewer 엔진으로 렌더링했습니다. 별도 에이전트가 구조·라우팅 테스트와 이미지 검수를 수행했고, 발견한 오류를 수정한 뒤 다시 검증했습니다. 아래 수치는 이 다섯 예제의 결과이며 임의 아키텍처 전체에 대한 성능 보장은 아닙니다.

## 개선 전후

| 사례 | 선 교차 전 → 후 | 선 중첩 길이 전 → 후 | 편집 가능한 원본 | 미리보기 |
|---|---:|---:|---|---|
| AWS 2 AZ | 3 → 0 | 24 → 0 px | [drawio](../examples/aws-three-tier.drawio) | [PNG](../examples/aws-three-tier.png) |
| AWS 한글 | 3 → 0 | 24 → 0 px | [drawio](../examples/aws-three-tier-ko.drawio) | [PNG](../examples/aws-three-tier-ko.png) |
| AWS 3 AZ 앱 / 2 AZ DB | 14 → 2 | 158 → 0 px | [drawio](../examples/aws-three-az.drawio) | [PNG](../examples/aws-three-az.png) |
| Azure regional | 2 → 0 | 14 → 0 px | [drawio](../examples/azure-regional.drawio) | [PNG](../examples/azure-regional.png) |
| GCP regional | 3 → 0 | 16 → 0 px | [drawio](../examples/gcp-regional.drawio) | [PNG](../examples/gcp-regional.png) |
| 합계 | **25 → 2** | **236 → 0 px** | | |

기존 경로와 새 경로를 동일한 지표 함수로 측정했습니다. 교차는 서로 다른 엣지 쌍의 교차 좌표를 세며, 두 엣지의 공통 종점은 제외합니다. 중첩 길이는 엣지 쌍별로 같은 직선 구간을 공유하는 길이의 합입니다. 박스 경계와의 교차는 통신선 교차 지표에 포함하지 않습니다.

이 비교에는 라우터 개선과 템플릿의 포트·여백·제목 위치 조정이 함께 포함됩니다. 라우터 단독 비교는 아닙니다. 전체 꺾임 수는 92 → 97로 늘었습니다. 짧은 경로보다 명확한 연결 지점과 분리된 선을 우선한 결과입니다. [기존 경로·이미지](before-routing/)와 [기존 수치](routing-before.json)를 보관했습니다.

3-AZ의 남은 두 교차는 DB로 향하는 서로 독립적인 경로입니다. 실제 렌더에서 점프 아크 2개를 확인했고, 생성 보고서에 검수 경고로 남겼습니다. 경고를 숨기거나 교차를 연결 지점으로 바꾸지 않았습니다.

## 검증한 항목

- 회귀 테스트 **43개 통과**. 카드·제목 장애물, 포트 분산, 명시 포트 예약, 모든 선에 대한 라벨 충돌, 입력 엣지 순서 독립성, XML 참조, 잘못된 입력, CSP 경계, 한글 텍스트 길이, 추가 AZ에 가려지는 논리 그룹을 검사합니다.
- 공식 스킬 검사: Skill is valid!
- 5개 예제 총 **59개 연결선과 59개 라벨**의 실제 렌더 좌표가 생성 보고서와 일치합니다. 라벨 앵커는 draw.io의 픽셀 반올림을 고려해 0.51 px 허용합니다.
- 5개 렌더 모두 JavaScript 오류·누락 아이콘·깨진 이미지 0.
- 실제 Graph 모델에서 연결된 리소스를 이동·복원하고, 라벨이 있는 연결선과 양 끝점을 함께 이동하여 라벨이 따라오는지 확인했습니다. XML 저장·재파싱 후 source/target와 라벨의 상대 부모 관계도 보존됩니다.
- 별도 [교차 fixture](fixtures/routing-crossings.png)로 한 번 교차하는 두 선의 점프 아크를 확인했습니다. 모델 지표 1회, 실제 렌더 마커 1개가 일치합니다.
- PNG 전체와 복잡한 영역을 눈으로 검수했습니다. AWS 3-AZ는 별도 검수에서 발견한 그룹 경계 가림을 수정하고 재렌더링했습니다.

기계 판독 결과, 모델 해시, viewer SHA-256: [results.json](results.json). 각 예제 옆에 모델, SVG, 생성 보고서, 렌더 보고서가 함께 있습니다.

## 이번 반복에서 고친 문제

1. 같은 카드 측면의 입·출력 선이 한 점에 몰림 → 양방향 연결을 함께 분산하고 수동 포트를 먼저 예약합니다.
2. 선이 기존 선과 포개짐 → 양의 길이를 공유하는 경로를 금지하고, 교차·꺾임·가까운 평행선에 비용을 부여합니다.
3. 먼저 배치한 라벨을 나중 선이 관통 → 모든 경로를 만든 후 전체 선·리소스·제목·경계와 충돌 검사합니다.
4. 라벨이 독립 텍스트여서 선 편집 시 남겨짐 → 실제 연결선의 상대 좌표 자식 셀로 만들었습니다.
5. AWS 3-AZ 추가 시 서브넷 배경이 논리 그룹을 덮음 → 부모 순서를 지키면서 일반 컨테이너보다 overlay를 나중에 그립니다.
6. 관리형 서비스가 하위 그룹을 거쳐 서브넷 안에 숨음 → 전체 상위 경계를 검사합니다. Azure/GCP 서브넷의 리전 범위와 공급자별 VPC/VNet도 검사합니다.
7. 예약 ID, 잘못된 형식·좌표, 긴 페이지/범례 텍스트 → 생성 전에 수정 가능한 오류로 보고합니다.
8. Azure의 모호한 Gateway subnet → App Gateway subnet; GCP 로드밸런서에는 global external ALB 모드를 명시했습니다.

## 재현 및 범위

회귀 테스트: `python3 -m unittest discover -s evals -v`

예제 재생성: `python3 cloud-architecture-drawio/scripts/cloud_drawio.py build examples/aws-three-az.model.json examples/aws-three-az.drawio`

렌더 재현은 [절차](../cloud-architecture-drawio/references/rendering.md)를 따릅니다. 기존 Node/Playwright 설치와 기록된 viewer를 사용할 수 있습니다.

- 36개 CSP 벡터 아이콘을 포함합니다. 전체 최신 아이콘 목록은 아니며, GCP는 draw.io gcp2 계열입니다.
- 에이전트가 배치와 의미를 선택하고 생성기가 경로를 계산합니다. 임의 규모 자동 배치나 전역 최적 경로를 보장하지 않습니다. 복잡한 토폴로지는 페이지 분리 또는 native XML 편집이 필요할 수 있습니다.
- 일부 구조·서비스 범위 검증이며 실제 라우팅·방화벽·DNS 도달 가능성 검증은 아닙니다. AWS NAT의 상세 egress와 서브넷 attachment는 예제 주석대로 생략했습니다.
- draw.io Desktop이 없어 실제 viewer의 Graph 엔진에서 검증했습니다. 데스크톱 에디터 UI 수동 조작 테스트와는 구분합니다.
- 편집 가능한 waypoint를 저장하므로 이후 수동으로 도형을 이동하면 주변 전체 선의 최적화·충돌 검사가 자동 실행되지는 않습니다. 모델 기반 변경은 재빌드·재렌더링하고, 수동 편집본은 원본을 보존해 필요한 셀만 수정합니다.

## 설치 확인 — 2026-09-29

개인 스킬 폴더에 v2를 설치하고 배포 파일 55개의 내용이 작업본과 일치함을 확인했습니다. 설치 경로의 Azure 템플릿 빌드가 경고 없이 성공했고, 공식 스킬 검사도 통과했습니다. 기존 설치본은 작업 폴더의 `.cache/installed-skill-before-v2`에 백업했습니다.
