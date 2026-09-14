"""프롬프트 매트릭스 정의와 프롬프트 합성 — /api 함수들이 공유하는 모듈.

파일명이 `_` 로 시작하므로 Vercel 이 엔드포인트로 만들지 않는다.
매트릭스 5축(분야·콘텐츠 유형·이미지 유형·카테고리·톤)의 선택값을 받아
[공통 접근성 규칙] + [분야] + [이미지 유형] + [카테고리] + [톤] + [길이·언어] 블록을 합성한다.
"""

# ---- 매트릭스 축 정의 (폐쇄 enum) ------------------------------------------------
# 각 항목: (키, 화면 표시명, 프롬프트 블록)

DOMAINS = [
    ("ecommerce", "쇼핑몰", "이 이미지는 온라인 쇼핑몰의 상품 관련 이미지다. 구매 판단에 필요한 정보(제품명·구성·용량·수치·라벨 문구)를 중요도 순으로 전달한다."),
    ("press", "언론사", "이 이미지는 언론사 기사에 실리는 보도 이미지다. 눈으로 확인되는 사실만 중립적으로 서술하고, 인물의 감정·의도·정치 성향·신원을 추측하지 않는다. 인물 이름은 제공된 컨텍스트에 있을 때만 쓴다."),
    ("public", "공공기관", "이 이미지는 공공기관·지자체의 안내 이미지다. 일정·장소·대상·신청 방법·문의처 같은 행정 정보를 빠짐없이, 원문 표기 그대로 전달한다."),
    ("education", "교육", "이 이미지는 교육 자료(강의·교재·학습 콘텐츠)다. 학습자가 내용을 따라갈 수 있도록 개념·순서·관계를 명확히 설명한다."),
    ("culture", "문화예술", "이 이미지는 전시·공연·작품 관련 이미지다. 작품의 구도·색·재료·분위기를 사실 위주로 묘사하되 해석은 짧게 한다."),
    ("sns", "SNS·블로그", "이 이미지는 SNS·블로그 게시물의 이미지다. 게시 맥락에서 독자가 궁금해할 핵심(무엇을·어디서·어떤 상황)을 간결히 전달한다."),
]

CONTENT_TYPES = [
    ("product", "상품", "콘텐츠 유형은 상품 소개다. 제품의 이름·종류·색상·수량·특징을 우선한다."),
    ("article", "기사·글", "콘텐츠 유형은 기사 또는 글에 딸린 이미지다. 본문을 보완하는 시각 정보를 전달한다."),
    ("notice", "공지·안내", "콘텐츠 유형은 공지·안내문이다. 날짜·시간·장소·대상·방법을 정확히 옮긴다."),
    ("promotion", "홍보·광고", "콘텐츠 유형은 홍보·광고다. 광고 문구는 있는 그대로 옮기되 과장 표현을 덧붙이지 않는다."),
    ("lecture", "강의·교재", "콘텐츠 유형은 강의·교재 자료다. 도식·순서·핵심 용어를 빠뜨리지 않는다."),
]

IMAGE_KINDS = [
    ("photo", "일반 사진", "이미지 유형은 일반 사진이다. 피사체·배경·구도·행동을 사실대로 묘사한다."),
    ("product_detail_image", "상품 상세 이미지", "이미지 유형은 상품 상세 페이지 이미지다. 이미지 안의 텍스트·표·수치를 순서대로 원문 그대로 옮기고, 표는 '항목: 값' 문장으로 푼다."),
    ("poster", "포스터·배너", "이미지 유형은 포스터·배너다. 제목→일시→장소→대상→문의 순으로 적힌 문구를 원문 그대로 옮긴다."),
    ("long_text", "긴 글 이미지", "이미지 유형은 긴 글이 들어간 이미지다. 적힌 글 전문을 순서대로 원문 보존해 옮기고 요약하지 않는다. 원문 보존이 분량 규칙보다 우선한다."),
    ("infographic", "인포그래픽·차트", "이미지 유형은 인포그래픽·차트다. 제목·축·범례·수치와 그것이 보여주는 추세를 문장으로 설명한다."),
    ("screenshot", "화면 캡처", "이미지 유형은 화면 캡처다. 어떤 화면인지, 보이는 텍스트·버튼·상태를 순서대로 설명한다."),
]

CATEGORIES = [
    ("general", "일반", ""),
    ("food", "식품", "식품이므로 원재료·용량·원산지·알레르기 유발 물질·유통기한 표시가 보이면 전부 원문 그대로 보존한다."),
    ("apparel", "의류·패션", "의류이므로 종류·색상·소재·핏·사이즈 표기·착용 상황을 전달한다."),
    ("electronics", "전자기기", "전자기기이므로 모델명·규격·수치·포트·구성품을 정확히 옮긴다."),
    ("cosmetics", "화장품", "화장품이므로 제품 종류·용량·주요 성분·사용 부위·주의 문구를 보존한다."),
    ("economy", "경제", "경제 기사 이미지이므로 수치·그래프·기업명·통화 단위를 정확히 읽는다."),
    ("politics", "정치", "정치 기사 이미지이므로 장소·행사·발언 상황만 서술하고 평가·추측을 하지 않는다."),
    ("sports", "스포츠", "스포츠 이미지이므로 종목·경기 상황·동작·유니폼·점수판 정보를 서술한다."),
    ("entertainment", "연예·문화", "연예·문화 이미지이므로 행사·무대·의상·분위기를 서술하되 외모 평가를 하지 않는다."),
    ("event", "행사·공모전", "행사·공모전 이미지이므로 행사명·기간·장소·대상·접수 방법·문의처를 빠짐없이 옮긴다."),
    ("people", "인물", "인물 이미지이므로 인원·복장·자세·행동·배경을 서술하고 나이·감정·신원은 추측하지 않는다."),
]

TONES = [
    ("plain", "담백", "문체는 담백하게: 수식어와 감탄을 빼고 명사 중심으로 사실만 쓴다."),
    ("formal", "격식", "문체는 격식 있게: '~입니다/~합니다' 체의 공식 문서 톤으로 쓴다."),
    ("friendly", "친근", "문체는 친근하게: 부드러운 '~해요' 체로 쓰되 정보는 빠뜨리지 않는다."),
]

LENGTHS = [
    ("short", "짧게 (80자 이내)", "alt_text 는 80자 이내 한 문장으로 쓴다. long_description 은 이미지에 텍스트나 복잡한 정보가 없으면 빈 문자열로 둔다."),
    ("standard", "보통 (150자 이내)", "alt_text 는 150자 이내 1~2문장으로 쓴다. long_description 에는 필요한 경우 300자 이내로 보충 설명을 쓴다."),
    ("detailed", "자세히 (텍스트 전문 포함)", "alt_text 는 150자 이내로 핵심을 쓰고, long_description 에 이미지 안의 정보를 빠짐없이 1,000자 이내로 정리한다."),
]

LANGUAGES = [
    ("ko", "한국어", "모든 출력은 한국어로 쓴다. 단위·약어는 스크린리더가 읽기 쉽도록 풀어 쓴다(예: 'ml' → '밀리리터')."),
    ("en", "English", "Write every field in natural English suitable for screen readers."),
]

AXES = {
    "domain": DOMAINS,
    "content_type": CONTENT_TYPES,
    "image_kind": IMAGE_KINDS,
    "category": CATEGORIES,
    "tone": TONES,
    "length": LENGTHS,
    "language": LANGUAGES,
}

DEFAULTS = {
    "domain": "ecommerce", "content_type": "product", "image_kind": "photo",
    "category": "general", "tone": "plain", "length": "standard", "language": "ko",
}

COMMON_RULES = """당신은 시각장애인이 스크린리더로 듣게 될 이미지 대체텍스트(alt text)를 쓰는 접근성 전문가다.
공통 규칙:
1. 이미지에 실제로 보이는 것만 쓴다. 보이지 않는 제품 효능·의도·감정·정체를 지어내지 않는다.
2. 이미지 안에 글자가 있으면 그 문구를 원문 그대로 옮긴다. 요약하거나 순서를 바꾸지 않는다.
3. '이미지', '사진입니다' 같은 군더더기, 이모지, 별표·대괄호 같은 장식 기호, 마크다운 서식을 쓰지 않는다.
4. 첫 문장에 가장 중요한 정보를 둔다. 분량은 이미지의 실제 정보량에 비례한다.
5. 흰 배경·단색 면처럼 의미 없는 이미지는 보이는 그대로 한 문장으로 쓰고 is_decorative 를 true 로 둔다.
6. 작업 상황 설명, 사과, 안내 문구를 출력에 넣지 않는다."""

OUTPUT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "alt_text": {"type": "STRING"},
        "long_description": {"type": "STRING"},
        "detected_text": {"type": "STRING"},
        "is_decorative": {"type": "BOOLEAN"},
    },
    "required": ["alt_text", "long_description", "detected_text", "is_decorative"],
}


def options():
    """프론트가 select 를 채울 때 쓰는 축별 선택지 (키·표시명만)."""
    return {
        axis: [{"key": key, "label": label} for key, label, _ in items]
        for axis, items in AXES.items()
    } | {"defaults": DEFAULTS}


def normalize(selection):
    """요청의 매트릭스 선택값을 검사한다.

    생략된 축은 조용히 기본값을 쓰고, 목록에 없는 값은 기본값으로 대체한 뒤 대체 목록에 남긴다.
    """
    result, replaced = {}, []
    for axis, items in AXES.items():
        keys = {key for key, _, _ in items}
        value = str((selection or {}).get(axis, "") or "").strip()
        if value and value not in keys:
            replaced.append(f"{axis}={value}→{DEFAULTS[axis]}")
            value = ""
        result[axis] = value or DEFAULTS[axis]
    return result, replaced


def matrix_key(sel):
    """canonical 표기: domain.content_type.image_kind.category.tone"""
    return ".".join(sel[a] for a in ("domain", "content_type", "image_kind", "category", "tone"))


def _block(axis, key):
    for k, _, text in AXES[axis]:
        if k == key:
            return text
    return ""


def compose_prompt(sel, context=""):
    """블록을 합성해 최종 프롬프트와 사용된 블록 목록을 돌려준다."""
    blocks = [("공통 접근성 규칙", COMMON_RULES)]
    for axis, title in (("domain", "분야"), ("content_type", "콘텐츠 유형"), ("image_kind", "이미지 유형"),
                        ("category", "카테고리"), ("tone", "톤"), ("length", "길이"), ("language", "언어")):
        text = _block(axis, sel[axis])
        if text:
            blocks.append((f"{title}: {sel[axis]}", text))
    context = (context or "").strip()[:500]
    if context:
        blocks.append(("요청 컨텍스트", f"이미지가 쓰이는 맥락(제목·캡션·설명): {context}\n컨텍스트는 참고만 하고, 이미지에 없는 내용을 컨텍스트에서 가져와 단정하지 않는다."))
    blocks.append(("출력 형식", "JSON 객체 하나만 출력한다: alt_text(대체텍스트), long_description(보충 설명, 불필요하면 빈 문자열), detected_text(이미지 안에 적힌 글 전문, 없으면 빈 문자열), is_decorative(장식용 여부)."))
    prompt = "\n\n".join(f"[{title}]\n{text}" for title, text in blocks)
    return prompt, [title for title, _ in blocks]
