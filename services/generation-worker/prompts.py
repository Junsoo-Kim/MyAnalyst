# prompts.py

import re

# BASE_PROMPT_TEXT를 여러 부분으로 분리하여 동적으로 구성할 수 있게 함

# 배경 정보 템플릿
BACKGROUND_TEMPLATE = """
[배경 정보]

- 분석 대상 기업: {company}
- 현재 시점: {current_time}
"""

# 목표 템플릿 
GOAL_TEMPLATE = """
[목표]

{company}의 {date} 실적 분석 및 향후 전망에 대한 종합적인 기업 분석 보고서({title})를 생성하는 것입니다.
"""

# 보고서 작성 가이드라인 템플릿
GUIDELINES_TEMPLATE = """
[보고서 작성 가이드라인]

- 정보 출처 명확화: 보고서의 모든 내용은 오직 RAG를 통해 제공된 컨텍스트에만 근거해야 합니다. 컨텍스트에 명시적으로 언급되지 않은 외부 정보, 추측, 또는 개인적인 의견을 포함하지 마십시오.
- 객관성 유지: 사실에 기반하여 객관적이고 중립적인 톤으로 서술하십시오.
- 구조화: 아래 제시된 구조에 따라 정보를 논리적으로 구성하여 보고서를 작성하십시오.
"""

# 보고서 구조 및 포함 내용 지침 템플릿 - 동적으로 장(chapter)을 받아서 사용
STRUCTURE_TEMPLATE = """
[생성할 보고서의 구조 및 포함 내용 지침]

다음 구조를 따라 보고서를 작성하되, 각 섹션에 해당하는 내용을 제공된 컨텍스트(공시, 뉴스 기사)에서 찾아서 요약하고 기술하십시오.

{chapters}

{indicator_section}
"""

# 관심 지표가 있을 때 추가할 내용
INDICATOR_TEMPLATE = """
[관심 지표]

보고서 작성 시 특별히 다음 지표에 대한 정보를 중점적으로 다루세요: {indicator}
컨텍스트에서 해당 지표에 관한 정보를 찾아 적절한 섹션에 포함시키고, 가능하다면 해당 지표의 변화 추이와 의미를 설명하세요.
"""

# 섹션별 평가 기준 템플릿
SECTION_EVALUATION_TEMPLATE = """
[{section_number}. {section_title} 평가 기준]

{evaluation_criteria}
"""

# 보고서 평가 기준 템플릿
EVALUATION_TEMPLATE = """
[보고서 평가 기준]

평가 목표: 생성된 보고서가 주어진 컨텍스트({company}의 {date} 공시 자료 및 관련 뉴스 기사)의 정보를 얼마나 정확하고 충실하게, 그리고 구조적으로 잘 요약했는지 평가합니다.

종합 평가 기준 (모든 목차 공통 적용):

1. 컨텍스트 충실성 (Context Fidelity): 보고서의 모든 내용이 오직 제공된 컨텍스트 정보에만 기반하는가? 외부 정보나 환각(Hallucination)은 없는가? (가장 중요)
2. 구조 준수성 (Structural Adherence): 제시된 목차 구조를 정확히 따르고 있는가?
3. 객관성 및 톤 (Objectivity & Tone): 보고서 전체적으로 객관적이고 사실 기반의 중립적인 톤을 유지하는가? 추측이나 주관적 평가는 배제되었는가?
4. 명확성 및 가독성 (Clarity & Readability): 사용된 언어가 명확하고 이해하기 쉬운가? 정보가 각 목차 내에서 논리적으로 구성되어 있는가?

{section_evaluations}
"""

# 컨텍스트 정보가 부족할 때 사용할 대체 응답 템플릿
FALLBACK_CONTENT_TEMPLATE = """
컨텍스트 정보가 충분하지 않을 경우, 각 섹션에 대해 다음과 같은 형식으로 작성해 주세요:

[섹션 제목]에 대한 정보입니다. 이 섹션은 일반적으로 [섹션에 대한 일반적 설명]을 다루는 부분입니다.
현재 {company}의 {date} 보고서에서 이 부분에 대한 구체적인 데이터는 충분하지 않습니다.

향후 {company}의 보고서에서는 이 섹션에 [무엇을 포함하면 좋을지에 대한 제안] 내용이 포함되면 
보다 완성도 높은 분석이 가능할 것입니다.
"""

# 중첩 목차를 파싱하는 함수
def parse_nested_chapter(chapter_text):
    """
    중첩된 목차 구조를 파싱합니다.
    
    예: "1. 요약\n\n2. 분석\n  2.1 매출 분석\n  2.2 비용 분석" ->
    {
        "1": {"title": "요약", "subsections": {}},
        "2": {"title": "분석", "subsections": {
            "2.1": {"title": "매출 분석", "subsections": {}},
            "2.2": {"title": "비용 분석", "subsections": {}}
        }}
    }
    
    Returns:
        tuple: (전체 목차 구조 dict, 대목차 번호 목록, 요약 섹션 번호)
    """
    sections = {}
    main_sections = []  # 중복 없는 주요 섹션 번호 목록
    summary_section = None
    
    # 정규식 패턴
    main_section_pattern = re.compile(r'^(\d+)\.\s+(.+)$')
    sub_section_pattern = re.compile(r'^(\d+\.\d+)\s+(.+)$')
    
    # 목차를 라인별로 분리 (모든 유형의 줄바꿈 처리)
    lines = re.split(r'\n+', chapter_text)
    current_main_section = None
    
    for line in lines:
        line = line.strip()
        if not line:  # 빈 줄 건너뛰기
            continue
        
        # 들여쓰기 제거 및 수준 확인
        original_line = line
        indent_level = 0
        while line.startswith('  '):
            indent_level += 1
            line = line[2:]
        
        # 주요 섹션 패턴 확인 (예: "1. 제목")
        main_match = main_section_pattern.match(line)
        if main_match and indent_level == 0:
            section_num = main_match.group(1)
            section_title = main_match.group(2)
            
            # 중복 섹션 방지
            if section_num not in sections:
                sections[section_num] = {
                    "title": section_title,
                    "subsections": {}
                }
                main_sections.append(section_num)
                current_main_section = section_num
                
                # 요약 섹션 판단
                if "요약" in section_title or "Summary" in section_title.lower():
                    summary_section = section_num
            else:
                print(f"Warning: Duplicate section number {section_num} found. Using first occurrence.")
            
            continue
        
        # 하위 섹션 패턴 확인 (예: "1.1 제목" 또는 "  1.1 제목")
        sub_match = sub_section_pattern.match(line)
        if sub_match or (indent_level > 0 and '.' in line):
            # 정규식에 매치되면 그 결과 사용, 아니면 직접 파싱
            if sub_match:
                sub_num = sub_match.group(1)
                sub_title = sub_match.group(2)
            else:
                parts = line.split('.', 1)
                if len(parts) == 2:
                    sub_num = parts[0].strip()
                    # 하위 섹션 번호에 메인 섹션 번호가 포함되어 있는지 확인
                    if '.' not in sub_num and current_main_section:
                        sub_num = f"{current_main_section}.{sub_num}"
                    sub_title = parts[1].strip()
                else:
                    continue  # 유효한 하위 섹션 형식이 아님
            
            # 현재 처리 중인 주요 섹션이 있는지 확인
            if current_main_section and current_main_section in sections:
                # 하위 섹션 번호가 주요 섹션 번호로 시작하는지 검증
                main_prefix = current_main_section + "."
                if sub_num.startswith(main_prefix) or indent_level > 0:
                    sections[current_main_section]["subsections"][sub_num] = {
                        "title": sub_title,
                        "subsections": {}
                    }
    
    # 주요 섹션 번호 중복 제거
    main_sections = list(dict.fromkeys(main_sections))
    
    # 요약 섹션이 명시적으로 없으면 첫번째 섹션을 요약으로 간주
    if not summary_section and main_sections:
        summary_section = main_sections[0]
    
    # 파싱 결과 로깅
    print(f"Parsed {len(sections)} main sections: {list(sections.keys())}")
    for sec_num, sec_data in sections.items():
        subsec_count = len(sec_data["subsections"])
        if subsec_count > 0:
            print(f"  Section {sec_num} has {subsec_count} subsections: {list(sec_data['subsections'].keys())}")
    
    return sections, main_sections, summary_section

# 전체 프롬프트를 동적으로 구성하는 함수
def build_base_prompt(title, company, date, chapter, indicator="none", evaluations=""):
    """
    사용자 입력을 바탕으로 동적으로 BASE_PROMPT_TEXT를 구성합니다.
    
    Args:
        title: 보고서 제목
        company: 분석 대상 기업
        date: 분석 시기
        chapter: 목차 문자열 (중첩 구조 가능)
        indicator: 관심 지표
        evaluations: 섹션별 평가 기준 (\n\n으로 구분)
    """
    from datetime import datetime
    current_time = datetime.now().strftime("%Y년 %m월 %d일")
    
    # 목차 파싱
    sections, main_section_nums, _ = parse_nested_chapter(chapter)
    
    # 포맷팅된 목차 문자열 생성
    chapters_formatted = ""
    for section_num in main_section_nums:
        section = sections.get(section_num)
        if section:
            chapters_formatted += f"{section_num}. {section['title']}\n"
            
            # 하위 섹션이 있으면 들여쓰기하여 추가
            subsections = section.get("subsections", {})
            for sub_num, sub_section in subsections.items():
                chapters_formatted += f"  {sub_num} {sub_section['title']}\n"
    
    # 관심 지표가 있을 경우에만 해당 섹션 추가
    indicator_section = ""
    if indicator and indicator.lower() != "none":
        indicator_section = INDICATOR_TEMPLATE.format(indicator=indicator)
    
    # 섹션별 평가 기준 처리
    section_evaluations = ""
    if evaluations:
        # \n\n으로 구분된 각 섹션의 평가 기준을 분리
        eval_sections = evaluations.split("\n\n")
        
        # 각 섹션에 해당하는 평가 기준을 매핑 (순서대로)
        for i, section_num in enumerate(main_section_nums):
            if i < len(eval_sections):
                section = sections.get(section_num)
                if section:
                    section_title = section["title"]
                    section_evaluations += SECTION_EVALUATION_TEMPLATE.format(
                        section_number=section_num,
                        section_title=section_title,
                        evaluation_criteria=eval_sections[i]
                    ) + "\n\n"
    
    # 모든 템플릿 조합
    complete_prompt = (
        BACKGROUND_TEMPLATE.format(company=company, current_time=current_time) + "\n" +
        GOAL_TEMPLATE.format(company=company, date=date, title=title) + "\n" +
        GUIDELINES_TEMPLATE + "\n" +
        STRUCTURE_TEMPLATE.format(chapters=chapters_formatted, indicator_section=indicator_section) + "\n" +
        EVALUATION_TEMPLATE.format(
            company=company, 
            date=date, 
            section_evaluations=section_evaluations
        )
    )
    
    return complete_prompt

# 기존 BASE_PROMPT_TEXT는 레거시 지원용으로 유지
BASE_PROMPT_TEXT = """
[배경 정보]

- 분석 대상 기업: 셀트리온
- 현재 시점: 2025년 1월 1일

[목표]

셀트리온의 24년 4분기 실적 분석 및 향후 전망에 대한 종합적인 기업 분석 보고서를 생성하는 것입니다.

[보고서 작성 가이드라인]

- 정보 출처 명확화: 보고서의 모든 내용은 오직 RAG를 통해 제공된 컨텍스트에만 근거해야 합니다. 컨텍스트에 명시적으로 언급되지 않은 외부 정보, 추측, 또는 개인적인 의견을 포함하지 마십시오.
- 객관성 유지: 사실에 기반하여 객관적이고 중립적인 톤으로 서술하십시오.
- 구조화: 아래 제시된 구조에 따라 정보를 논리적으로 구성하여 보고서를 작성하십시오.

[생성할 보고서의 구조 및 포함 내용 지침]

다음 구조를 따라 보고서를 작성하되, 각 섹션에 해당하는 내용을 제공된 컨텍스트(공시, 뉴스 기사)에서 찾아서 요약하고 기술하십시오.

1. 보고서 요약 (Executive Summary):
    - 컨텍스트에 기반한 셀트리온 4Q24 실적의 주요 특징 요약.
    - 컨텍스트에서 파악된 향후 사업 방향 또는 전망에 대한 핵심 내용 요약.
2. 2024년 4분기 실적 분석:
    - 실적 요인 분석: 공시 내용이나 뉴스 기사에서 언급된 4Q24 실적의 주요 변동 요인(긍정적/부정적 요인 모두)을 설명. (예: 특정 제품의 판매 호조/부진, 비용 증가/감소 요인, 일회성 손익 발생 등 공식적으로 언급된 내용)
3. 주요 사업 및 제품 동향:
    - 제품 관련 소식: 컨텍스트에서 언급된 주요 제품(예: 램시마SC, 유플라이마, 베그젤마, 짐펜트라, 스테키마 등) 관련 최신 동향(예: 주요 시장 출시/허가 현황, 판매 관련 언급, 생산 관련 소식 등)을 요약.
    - R&D 및 파이프라인: 컨텍스트에서 찾을 수 있는 신약 개발 진행 상황, 임상 결과 발표, 기술 도입 등 R&D 관련 중요 업데이트 사항을 기술.
    - CMO 사업: 위탁생산(CMO) 관련 계약, 생산 등 컨텍스트 내 관련 정보를 요약.
    - 기타 사업: 합병 관련 진행 상황 및 시너지 창출 노력 등 컨텍스트 내 기타 중요 사업 내용을 포함.
4. 시장 환경 및 전략 방향:
    - 주요 시장 활동: 컨텍스트에 나타난 주요 시장(예: 미국, 유럽)에서의 활동 내용(예: 신제품 출시, 허가 신청, 마케팅 활동, 시장 경쟁 관련 언급 등)을 요약.
    - 회사의 공식 전략: 컨텍스트의 공시나 보도자료 등에서 발표된 회사의 주요 경영 전략, 투자 계획, 파트너십 체결 등 내용을 정리.
5. 향후 전망 (공식 발표 기반):
    - 회사의 공식 입장/계획: 컨텍스트에서 확인되는 2025년 사업 계획, 목표, 신제품 출시 예정, 성장 전략 등 회사에서 공식적으로 발표한 향후 전망 관련 내용을 요약. (애널리스트의 예측이 아닌, 회사의 발표 내용 중심)
    - 미래 성과 영향 요인: 컨텍스트 정보를 바탕으로 향후 실적에 영향을 미칠 수 있는 주요 요인(예: 신제품 성과 기대, 진행 중인 R&D 중요성, 시장 환경 변화 등 공식 발표나 뉴스에서 강조된 내용)을 정리.
6. 기타 참고사항:
    - 컨텍스트(공시, 뉴스 기사)에서 언급된 기타 중요 정보, 잠재적 위험 요인 또는 기회 요인 등을 객관적으로 요약. (투자 추천이나 가치 판단은 제외)

[보고서 평가 기준]

평가 목표: 생성된 보고서가 주어진 컨텍스트(셀트리온 4Q24 공시 자료 및 관련 뉴스 기사)의 정보를 얼마나 정확하고 충실하게, 그리고 구조적으로 잘 요약했는지 평가합니다.

종합 평가 기준 (모든 목차 공통 적용):

1. 컨텍스트 충실성 (Context Fidelity): 보고서의 모든 내용이 오직 제공된 컨텍스트 정보에만 기반하는가? 외부 정보나 환각(Hallucination)은 없는가? (가장 중요)
2. 구조 준수성 (Structural Adherence): 제시된 6가지 목차 구조를 정확히 따르고 있는가?
3. 객관성 및 톤 (Objectivity & Tone): 보고서 전체적으로 객관적이고 사실 기반의 중립적인 톤을 유지하는가? 추측이나 주관적 평가는 배제되었는가?
4. 명확성 및 가독성 (Clarity & Readability): 사용된 언어가 명확하고 이해하기 쉬운가? 정보가 각 목차 내에서 논리적으로 구성되어 있는가?

목차별 세부 평가 기준:

1. 보고서 요약 (Executive Summary)

- 핵심 내용 반영도: 보고서 본문(2~6번 목차)의 핵심 내용(4Q24 실적 주요 특징, 향후 전망 핵심)을 정확하게 요약하고 있는가?
- 정확성 및 일관성: 요약된 내용이 컨텍스트 및 보고서 본문의 내용과 일치하며 왜곡이 없는가?
- 간결성: 핵심 내용을 간결하게 전달하는가? 불필요하게 상세하지 않은가?
- 포괄성: 실적 측면과 전망 측면을 균형 있게 포함하는가?

2. 2024년 4분기 실적 분석 (4Q24 Performance Review)

- 실적 요인 분석 정확성: 실적 변동 요인(매출 동인, 비용 요인 등) 설명이 컨텍스트(공시, 뉴스) 내용과 정확히 일치하는가?
- 실적 요인 분석 완전성: 컨텍스트에서 언급된 *중요한* 실적 변동 요인을 충분히 다루고 있는가?
- 컨텍스트 기반: 분석 내용이 컨텍스트 정보에만 근거하며 외부 해석이 배제되었는가?

3. 주요 사업 및 제품 동향 (Business & Product Developments)

- 정보 정확성: 제품 동향, R&D 업데이트, CMO 관련 기술 내용이 컨텍스트 정보와 사실적으로 일치하는가?
- 정보 완전성: 컨텍스트에서 언급된 주요 제품, R&D, CMO 관련 *중요* 업데이트 사항을 누락 없이 포함했는가?
- 관련성: 보고서 목차의 주제(사업 및 제품 동향)와 관련된 내용을 충실히 담고 있는가?
- 컨텍스트 기반: 내용이 컨텍스트(공시, 뉴스)에서 직접 확인 가능한 정보인가?

4. 시장 환경 및 전략 방향 (Market Environment & Strategy)

- 정보 정확성: 주요 시장(미국, 유럽 등) 활동 및 회사 전략(합병 시너지, 파트너십 등)에 대한 설명이 컨텍스트 정보와 일치하는가?
- 정보 완전성: 컨텍스트에서 강조된 주요 시장 활동 및 전략 방향을 충분히 포함하고 있는가?
- 관련성: 내용이 시장 환경 및 회사의 전략적 움직임에 초점을 맞추고 있는가?
- 컨텍스트 기반: 설명이 컨텍스트에서 제공된 정보의 범위를 벗어나지 않는가?

5. 향후 전망 (공식 발표 기반) (Future Outlook - Based on Official Statements)

- 공식 입장 정확성: 회사의 공식적인 향후 계획, 목표, 신제품 출시 일정 등을 컨텍스트 내용 그대로 정확하게 전달하는가?
- 공식 입장 완전성: 컨텍스트에서 언급된 회사의 *주요* 공식 전망 내용을 포함하고 있는가?
- 출처 명확성: 해당 내용이 회사의 '공식 발표'에 기반한 것임을 명확히 인지할 수 있게 서술되었는가? (추측성 서술과 구분되는가?)
- 컨텍스트 기반: 회사의 공식 발표 내용을 왜곡하거나 과장하지 않았는가?

6. 기타 참고사항 (Key Considerations - Based on Public Info)

- 정보 정확성: 언급된 참고사항(리스크, 기회 등)이 컨텍스트 정보에 사실적으로 기반하는가?
- 정보 완전성: 컨텍스트 내 다른 목차에 포함되지 않은 *중요한* 기타 정보, 리스크, 기회 요인을 포함하는가?
- 객관성: 투자 추천이나 주관적 가치 판단 없이, 사실 정보를 객관적으로 전달하는가?
- 관련성: 내용이 '기타 참고사항'으로서의 관련성을 가지는가?
- 컨텍스트 기반: 내용이 컨텍스트에서 직접 확인 가능한 정보인가?
"""

# 동적으로 키워드 프롬프트를 생성하는 함수
def create_keyword_prompt(section_number, section_title, company, date, top_k):
    """섹션에 맞는 키워드 생성 프롬프트를 동적으로 생성"""
    return f"""
{date} {company} 기업 분석 보고서를 만들기 위해 RAG 파이프라인을 활용할 것입니다.
벡터 DB인 Milvus에서 검색을 통해 상위 {top_k}개 청크를 가져올 것입니다.
보고서의 {section_number}번인 '{section_title}'을(를) 만들 때 필요한 검색을 위한 키워드를 제출하세요.
가능한 다양하고 관련성 높은 키워드를 포함해 주세요.
회사명({company})과 관련 제품명, 분기({date}), 실적, 재무, 사업, 전략 등의 키워드를 포함하세요.
결과를 출력할 때에는 키워드만 제출해주시고, 각 키워드들을 띄어쓰기로 구분하여 제출하세요.
"""

# 기존 프롬프트 템플릿은 레거시 지원을 위해 유지
MAKE_KEYWORD_PROMPT_TEMPLATE = """
24년 4분기 셀트리온 기업 분석 보고서를 만들기 위해 RAG 파이프라인을 활용할 것입니다.
벡터 DB인 Milvus에서 검색을 통해 상위 {top_k}개 청크를 가져올 것입니다.
보고서의 {section_number}번인 '{section_title}'을(를) 만들 때 필요한 검색을 위한 키워드를 제출하세요.
결과를 출력할 때에는 키워드만 제출해주시고, 각 키워드들을 띄어쓰기로 구분하여 제출하세요.
"""

# 동적으로 요약 프롬프트를 생성하는 함수
def create_summary_prompt(company, date, title):
    """보고서 내용에 맞는 요약 생성 프롬프트를 동적으로 생성"""
    return f"""
위 보고서는 당신이 만든 {company}의 {date} 분석 보고서 '{title}'의 본문 내용입니다.
이를 참고하여 보고서 요약을 작성해주세요.
반드시 보고서 요약(Executive Summary) 내용만 작성해야 합니다. 보고서 본문 내용은 포함하지 마십시오.
"""

# 기존 요약 프롬프트 템플릿은 레거시 지원을 위해 유지
MAKE_SUMMARY_PROMPT_TEMPLATE = """
위 보고서는 당신이 만든 2번부터 6번까지의 보고서 내용입니다.
이를 참고하여 보고서의 1번인 보고서 요약을 작성해주세요.
반드시 보고서 요약(Executive Summary) 내용만 작성해야 합니다. 보고서 본문 내용은 포함하지 마십시오.
"""