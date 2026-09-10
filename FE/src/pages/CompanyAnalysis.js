import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import './CompanyAnalysis.css'; // 별도의 CSS 파일 필요

const CompanyAnalysis = () => {
  const navigate = useNavigate();
  
  // 상태 관리 확장
  const [currentSlide, setCurrentSlide] = useState(1);
  const [totalSlides, setTotalSlides] = useState(5);
  const [selectedIndicators, setSelectedIndicators] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState(null);
  
  // 보고서 정보 관련 상태
  const [formData, setFormData] = useState({
    companyName: '',
    quarter: '2024년 4분기',
    title: '',
    titleOption: 'date-company'  // 'ai-generated' 옵션 제거, 기본값은 유지
  });
  
  // 선택된 섹션 추적
  const [selectedSections, setSelectedSections] = useState({
    section1: true,
    section2: true,
    section3: true,
    section4: true,
    section5: true
  });
  
  // 쿠키에서 userId 가져오기
  const getUserIdFromCookie = () => {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.startsWith('userId=')) {
        return cookie.substring('userId='.length);
      }
    }
    return null;
  };

  // refs
  const swiperRef = useRef(null);
  const companyNameRef = useRef(null);
  const quarterSelectRef = useRef(null);
  const customTitleRef = useRef(null);

  useEffect(() => {
    // AOS 초기화
    if (window.AOS) {
      window.AOS.init({
        duration: 600,
        easing: 'ease-in-out',
        once: true,
        mirror: false
      });
    }

    // Swiper 초기화
    let swiper = null;
    const initSwiper = setTimeout(() => {
      if (window.Swiper && swiperRef.current) {
        swiper = new window.Swiper('.analysis-swiper', {
          direction: 'horizontal',
          slidesPerView: 1,
          spaceBetween: 0,
          mousewheel: false,
          keyboard: {
            enabled: true,
          },
          pagination: {
            el: '.swiper-pagination',
            clickable: true,
            dynamicBullets: true,
            type: 'bullets',
          },
          autoHeight: false,
          allowTouchMove: true,
          on: {
            slideChange: function() {
              setCurrentSlide(this.activeIndex + 1);
            }
          }
        });
        
        setTotalSlides(swiper.slides.length);
      }
    }, 500);

    return () => {
      clearTimeout(initSwiper);
      if (swiper) {
        swiper.destroy();
      }
    };
  }, []);

  // 폼 입력 핸들러
  const handleInputChange = (e) => {
    const { id, value } = e.target;
    setFormData({
      ...formData,
      [id]: value
    });
  };
  
  // 드롭다운 변경 핸들러
  const handleSelectChange = (e) => {
    const { id, value } = e.target;
    setFormData({
      ...formData,
      [id]: e.target.options[e.target.selectedIndex].text
    });
  };
  
  // 제목 옵션 핸들러
  const handleTitleOptionChange = (e) => {
    const { value } = e.target;
    setFormData({
      ...formData,
      titleOption: value
    });
    toggleCustomTitleInput(value === 'custom');
  };

  // 제목 입력 필드 토글 함수
  const toggleCustomTitleInput = (show) => {
    const container = document.getElementById('customTitleContainer');
    if (container) {
      container.style.display = show ? 'block' : 'none';
    }
    
    updateTitlePreview();
  };

  // 제목 미리보기 업데이트 함수
  const updateTitlePreview = () => {
    const previewElement = document.getElementById('previewTitle');
    const selectedOption = formData.titleOption;
    
    if (!previewElement) return;
    
    let titleText = '';
    if (selectedOption === 'date-company') {
      titleText = `${formData.quarter} - ${formData.companyName || '기업명'}`;
    } else if (selectedOption === 'custom') {
      titleText = formData.title || '제목을 입력해주세요';
    }
    
    previewElement.textContent = titleText;
  };
  
  // 섹션 체크박스 토글 처리
  const handleSectionToggle = (e) => {
    const { id, checked } = e.target;
    const sectionId = id.replace('Check', '');
    
    setSelectedSections({
      ...selectedSections,
      [sectionId]: checked
    });
    
    // 서브섹션 체크박스 상태 업데이트
    toggleSubsections(e.target, `${sectionId}Subsections`);
  };

  // 모든 섹션 선택/해제 함수
  const selectAllSections = (selectAll) => {
    const updatedSections = {};
    Object.keys(selectedSections).forEach(key => {
      updatedSections[key] = selectAll;
    });
    
    setSelectedSections(updatedSections);
    
    // DOM의 체크박스 업데이트
    const allCheckboxes = document.querySelectorAll('input[type="checkbox"]');
    allCheckboxes.forEach(checkbox => {
      checkbox.checked = selectAll;
    });
  };

  // 챕터 정보 생성 함수
  const generateChapterText = () => {
    let chapterText = '';
    
    if (selectedSections.section1) {
      chapterText += '1. 보고서 요약\n';
      if (document.getElementById('section1_1Check')?.checked) {
        chapterText += ' 1.1 실적 주요 특징\n';
      }
      if (document.getElementById('section1_2Check')?.checked) {
        chapterText += ' 1.2 향후 전망 핵심\n';
      }
      chapterText += '\n';
    }
    
    if (selectedSections.section2) {
      chapterText += `2. ${formData.quarter} 실적 분석\n`;
      if (document.getElementById('section2_1Check')?.checked) {
        chapterText += ' 2.1 주요 재무 결과\n';
      }
      if (document.getElementById('section2_2Check')?.checked) {
        chapterText += ' 2.1 실적 요인 분석\n';
      }
      chapterText += '\n';
    }
    
    if (selectedSections.section3) {
      chapterText += '3. 주요 사업 및 제품 동향\n';
      if (document.getElementById('section3_1Check')?.checked) {
        chapterText += ' 3.1 제품 관련 소식\n';
      }
      if (document.getElementById('section3_2Check')?.checked) {
        chapterText += ' 3.2 R&D 및 파이프라인\n';
      }
      if (document.getElementById('section3_3Check')?.checked) {
        chapterText += ' 3.3 주요 사업\n';
      }
      if (document.getElementById('section3_4Check')?.checked) {
        chapterText += ' 3.4 기타 사업\n';
      }
      chapterText += '\n';
    }
    
    if (selectedSections.section4) {
      chapterText += '4. 시장 환경 및 전략 방향\n';
      if (document.getElementById('section4_1Check')?.checked) {
        chapterText += ' 4.1 주요 시장 활동\n';
      }
      if (document.getElementById('section4_2Check')?.checked) {
        chapterText += ' 4.2 회사의 공식 전략\n';
      }
      chapterText += '\n';
    }
    
    if (selectedSections.section5) {
      chapterText += '5. 향후 전망 (공식 발표 기반)\n';
      if (document.getElementById('section5_1Check')?.checked) {
        chapterText += ' 5.1 회사의 공식 입장/계획\n';
      }
      if (document.getElementById('section5_2Check')?.checked) {
        chapterText += ' 5.2 미래 성과 영향 요인\n';
      }
      chapterText += '\n';
    }
    
    return chapterText.trim();
  };

  // 보고서 제목 생성 함수
  const generateReportTitle = () => {
    if (formData.titleOption === 'custom' && formData.title) {
      return formData.title;
    } else {
      // 기본값으로 설정
      return `${formData.companyName} ${formData.quarter} 실적 분석 보고서`;
    }
  };

  // 요약 정보 업데이트
  const updateSummary = () => {
    const companyName = formData.companyName || '설정되지 않음';
    const quarterText = formData.quarter || '';
    const titleOption = formData.titleOption;
    const checkedSections = Object.values(selectedSections).filter(Boolean).length;
    
    document.getElementById('summaryCompanyName').textContent = companyName;
    document.getElementById('summaryQuarter').textContent = quarterText;
    
    let titleText = '';
    if (titleOption === 'date-company') {
      titleText = '날짜-기업명 형식';
    } else if (titleOption === 'custom') {
      titleText = formData.title || '직접 입력 (내용 없음)';
    }
    
    document.getElementById('summaryTitle').textContent = titleText;
    document.getElementById('summarySections').textContent = checkedSections;
    document.getElementById('summaryIndicators').textContent = 
      selectedIndicators.length > 0 ? `${selectedIndicators.length}개 선택됨` : '없음';
  };

  // 보고서 생성 함수
  const generateReport = async () => {
    // 유효성 검사
    if (!formData.companyName) {
      alert('기업명을 입력해주세요.');
      return;
    }

    // userid 가져오기
    const userId = getUserIdFromCookie();
    if (!userId) {
      alert('로그인이 필요합니다.');
      navigate('/login');
      return;
    }

    try {
      setIsGenerating(true);
      setError(null);
      
      // API 요청 데이터 준비
      const requestData = {
        userid: userId,
        company: formData.companyName,
        date: formData.quarter,
        title: generateReportTitle(),
        chapter: generateChapterText(),
        content: "none",
        indicator: selectedIndicators.length > 0 ? selectedIndicators.join(',') : "none",
        evaluation: "- 핵심 내용 반영도: 보고서 본문의 핵심 내용(실적 주요 특징, 향후 전망 핵심)을 정확하게 요약하고 있는가?\n- 정확성 및 일관성: 요약된 내용이 컨텍스트 및 보고서 본문의 내용과 일치하며 왜곡이 없는가?\n- 간결성: 핵심 내용을 간결하게 전달하는가? 불필요하게 상세하지 않은가?\n- 포괄성: 실적 측면과 전망 측면을 균형 있게 포함하는가?\n\n- 실적 요인 분석 정확성: 실적 변동 요인(매출 동인, 비용 요인 등) 설명이 컨텍스트 내용과 정확히 일치하는가?\n- 실적 요인 분석 완전성: 컨텍스트에서 언급된 중요한 실적 변동 요인을 충분히 다루고 있는가?\n- 컨텍스트 기반: 분석 내용이 컨텍스트 정보에만 근거하며 외부 해석이 배제되었는가?\n\n- 정보 정확성: 제품 동향, R&D 업데이트, CMO 관련 기술 내용이 컨텍스트 정보와 사실적으로 일치하는가?\n- 정보 완전성: 컨텍스트에서 언급된 주요 제품, R&D, CMO 관련 중요 업데이트 사항을 누락 없이 포함했는가?\n- 관련성: 보고서 목차의 주제(사업 및 제품 동향)와 관련된 내용을 충실히 담고 있는가?\n- 컨텍스트 기반: 내용이 컨텍스트(공시, 뉴스)에서 직접 확인 가능한 정보인가?\n\n- 정보 정확성: 주요 시장 활동 및 회사 전략에 대한 설명이 컨텍스트 정보와 일치하는가?\n- 정보 완전성: 컨텍스트에서 강조된 주요 시장 활동 및 전략 방향을 충분히 포함하고 있는가?\n- 관련성: 내용이 시장 환경 및 회사의 전략적 움직임에 초점을 맞추고 있는가?\n- 컨텍스트 기반: 설명이 컨텍스트에서 제공된 정보의 범위를 벗어나지 않는가?\n\n- 공식 입장 정확성: 회사의 공식적인 향후 계획, 목표, 신제품 출시 일정 등을 컨텍스트 내용 그대로 정확하게 전달하는가?\n- 공식 입장 완전성: 컨텍스트에서 언급된 회사의 주요 공식 전망 내용을 포함하고 있는가?\n- 출처 명확성: 해당 내용이 회사의 '공식 발표'에 기반한 것임을 명확히 인지할 수 있게 서술되었는가?\n- 컨텍스트 기반: 회사의 공식 발표 내용을 왜곡하거나 과장하지 않았는가?\n\n- 정보 정확성: 언급된 참고사항(리스크, 기회 등)이 컨텍스트 정보에 사실적으로 기반하는가?\n- 정보 완전성: 컨텍스트 내 다른 목차에 포함되지 않은 중요한 기타 정보, 리스크, 기회 요인을 포함하는가?\n- 객관성: 투자 추천이나 주관적 가치 판단 없이, 사실 정보를 객관적으로 전달하는가?\n- 관련성: 내용이 '기타 참고사항'으로서의 관련성을 가지는가?"
      };

      console.log('보고서 생성 요청 데이터:', requestData);
      
      // API 호출
      const response = await apiFetch('/report-jobs', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
        },
        body: JSON.stringify(requestData),
        credentials: 'include' // 쿠키 포함
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || '보고서 생성에 실패했습니다.');
      }

      // 성공 시 보고서 목록 페이지로 이동
      alert('보고서가 성공적으로 생성되었습니다.');
      const job = await response.json();
      navigate(`/report-job?id=${job.jobId}`);
      
    } catch (err) {
      console.error('보고서 생성 오류:', err);
      setError(err.message || '보고서 생성 중 오류가 발생했습니다.');
      alert(`오류: ${err.message || '보고서 생성에 실패했습니다.'}`);
    } finally {
      setIsGenerating(false);
    }
  };

  // 슬라이드 변경 시 실행되는 이펙트
  useEffect(() => {
    if (currentSlide === totalSlides) {
      updateSummary();
    } else if (currentSlide === 1) {
      // 1단계 슬라이드에서 현재 값 반영
      if (companyNameRef.current) {
        companyNameRef.current.value = formData.companyName;
      }
    }
  }, [currentSlide, totalSlides, formData]);

  // 섹션 토글 함수
  const toggleSubsections = (checkbox, subsectionId) => {
    const subsections = document.getElementById(subsectionId);
    if (!subsections) return;
    
    const checkboxes = subsections.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(box => {
      box.checked = checkbox.checked;
    });
  };

  // 이전 슬라이드로 이동
  const prevSlide = () => {
    const swiper = document.querySelector('.analysis-swiper')?.swiper;
    if (swiper) {
      swiper.slidePrev();
    }
  };

  // 다음 슬라이드로 이동
  const nextSlide = () => {
    const swiper = document.querySelector('.analysis-swiper')?.swiper;
    if (swiper) {
      swiper.slideNext();
    }
  };

  // 지표 토글 함수
  const toggleIndicator = (indicator) => {
    if (selectedIndicators.includes(indicator)) {
      setSelectedIndicators(selectedIndicators.filter(item => item !== indicator));
    } else {
      setSelectedIndicators([...selectedIndicators, indicator]);
    }
  };

  // 지표 검색 함수
  const searchIndicator = () => {
    const searchTerm = document.getElementById('indicatorSearch')?.value.trim().toLowerCase();
    const searchResults = document.getElementById('searchResults');
    const searchResultsList = document.getElementById('searchResultsList');
    
    if (!searchTerm || !searchResults || !searchResultsList) return;
    
    // 검색어가 없으면 검색 결과 숨김
    if (searchTerm === '') {
      searchResults.style.display = 'none';
      return;
    }
    
    // 검색어와 일치하는 지표 찾기
    const allIndicators = [
      "PER", "PBR", "EPS", "BPS", "ROE", "ROA", "EBITDA", "EV/EBITDA", "매출액성장률", 
      "영업이익률", "순이익률", "부채비율", "배당수익률", "FCF", "베타", 
      "PCR", "PSR", "GP마진", "OP마진", "유동비율", "당좌비율", "현금비율", 
      "이자보상배율", "자기자본비율", "총자본회전율", "매출채권회전율", "재고자산회전율"
    ];
    
    const filteredIndicators = allIndicators.filter(
      indicator => indicator.toLowerCase().includes(searchTerm)
    );
    
    // 검색 결과 표시
    searchResultsList.innerHTML = '';
    
    if (filteredIndicators.length > 0) {
      filteredIndicators.forEach(indicator => {
        const button = document.createElement('button');
        button.className = selectedIndicators.includes(indicator) 
          ? 'btn btn-sm btn-primary' 
          : 'btn btn-sm btn-outline-primary';
        button.dataset.indicator = indicator;
        button.textContent = indicator;
        button.onclick = () => toggleIndicator(indicator);
        searchResultsList.appendChild(button);
      });
      
      searchResults.style.display = 'block';
    } else {
      searchResultsList.innerHTML = '<p class="text-muted">검색 결과가 없습니다.</p>';
      searchResults.style.display = 'block';
    }
  };

  // 지표 제거 함수
  const removeIndicator = (indicator) => {
    setSelectedIndicators(selectedIndicators.filter(item => item !== indicator));
  };

  return (
    <main className="main">
      {/* Background Image */}
      <div className="hero-bg">
        <img src="/assets/img/hero-bg-light.webp" alt="" onError={(e) => e.target.src = '/assets/img/hero-bg.jpg'} />
      </div>
      
      {/* Company Analysis Swiper */}
      <div className="swiper analysis-swiper" ref={swiperRef}>
        <div className="swiper-wrapper">
          {/* Section 1 */}
          <section className="swiper-slide analysis-section" id="section1">
            <div className="container">
              <div className="section-content text-center">
                <h1 className="mb-5" data-aos="fade-up">기업 분석 - 1단계</h1>
                <div className="card shadow-lg border-0 p-4" data-aos="fade-up" data-aos-delay="100">
                  <h3>기본 정보 입력</h3>
                  <p className="mt-4">이 페이지에서는 분석할 기업의 기본 정보를 입력합니다.</p>
                  
                  {/* 기업명 입력 필드 개선 */}
                  <div className="mt-4 form-group">
                    <label htmlFor="companyName" className="form-label fw-bold">기업명</label>
                    <div className="input-group">
                      <span className="input-group-text"><i className="bi bi-building"></i></span>
                      <input 
                        type="text" 
                        className="form-control form-control-lg" 
                        id="companyName" 
                        ref={companyNameRef}
                        value={formData.companyName} 
                        onChange={handleInputChange}
                        placeholder="분석할 기업명을 입력하세요" 
                        required 
                      />
                    </div>
                    <div className="form-text text-muted">예: 삼성전자, 네이버, 카카오 등</div>
                  </div>
                  
                  {/* 날짜 선택 필드 추가 */}
                  <div className="mt-4 form-group">
                    <label htmlFor="quarterSelect" className="form-label fw-bold">분석 기준 분기</label>
                    <div className="input-group">
                      <span className="input-group-text"><i className="bi bi-calendar"></i></span>
                      <select 
                        className="form-select form-select-lg" 
                        id="quarterSelect"
                        ref={quarterSelectRef}
                        onChange={handleSelectChange}
                      >
                        <option value="24Q1">2024년 1분기</option>
                        <option value="24Q2">2024년 2분기</option>
                        <option value="24Q3">2024년 3분기</option>
                        <option value="24Q4" selected>2024년 4분기</option>
                        <option value="25Q1">2025년 1분기</option>
                        <option value="25Q2">2025년 2분기</option>
                      </select>
                    </div>
                    <div className="form-text text-muted">분석 기준 시점을 선택하세요</div>
                  </div>
                </div>
              </div>
            </div>
          </section>
          
          {/* Section 2 */}
          <section className="swiper-slide analysis-section" id="section2">
            <div className="container">
              <div className="section-content text-center">
                <h1 className="mb-5" data-aos="fade-up">기업 분석 - 2단계</h1>
                <div className="card shadow-lg border-0 p-4" data-aos="fade-up" data-aos-delay="100">
                  <h3>보고서 제목 설정</h3>
                  <p className="mt-4">보고서에 표시될 제목을 선택하세요.</p>
                  
                  {/* 보고서 제목 선택 옵션 - 2개로 변경하고 좌우 배치 */}
                  <div className="mt-4">
                    <div className="row">
                      {/* 옵션 1: 날짜-기업명 (기본값) - 왼쪽 컬럼 */}
                      <div className="col-md-6">
                        <div 
                          className={`card h-100 p-4 text-center option-card ${formData.titleOption === 'date-company' ? 'border-primary' : ''}`} 
                          onClick={() => handleTitleOptionChange({ target: { value: 'date-company' } })}
                          style={{ cursor: 'pointer' }}
                        >
                          <div className="form-check mb-3 d-flex justify-content-center">
                            <input 
                              className="form-check-input me-2" 
                              type="radio" 
                              name="titleOption" 
                              id="titleOption1" 
                              value="date-company" 
                              checked={formData.titleOption === 'date-company'}
                              onChange={handleTitleOptionChange}
                              onClick={(e) => e.stopPropagation()} // 이벤트 버블링 방지
                            />
                            <label className="form-check-label fw-bold" htmlFor="titleOption1">
                              날짜-기업명 형식
                            </label>
                          </div>
                          <div className="option-preview p-3 bg-light rounded mb-3">
                            <p className="text-muted small mb-1">미리보기:</p>
                            <p className="mb-0 fw-bold">{formData.companyName || '기업명'} {formData.quarter} 실적 분석 보고서</p>
                          </div>
                          <p className="text-muted small">
                            <i className="bi bi-info-circle me-1"></i>
                            기본 형식으로 보고서 제목이 생성됩니다.
                          </p>
                        </div>
                      </div>
                      
                      {/* 옵션 2: 직접 지정 - 오른쪽 컬럼 */}
                      <div className="col-md-6">
                        <div 
                          className={`card h-100 p-4 text-center option-card ${formData.titleOption === 'custom' ? 'border-primary' : ''}`}
                          onClick={() => handleTitleOptionChange({ target: { value: 'custom' } })}
                          style={{ cursor: 'pointer' }}
                        >
                          <div className="form-check mb-3 d-flex justify-content-center">
                            <input 
                              className="form-check-input me-2" 
                              type="radio" 
                              name="titleOption" 
                              id="titleOption3" 
                              value="custom"
                              checked={formData.titleOption === 'custom'}
                              onChange={handleTitleOptionChange}
                              onClick={(e) => e.stopPropagation()} // 이벤트 버블링 방지
                            />
                            <label className="form-check-label fw-bold" htmlFor="titleOption3">
                              직접 지정하기
                            </label>
                          </div>
                          <div id="customTitleContainer" className="mb-3" style={{ display: 'block' }}>
                            <div className="input-group" onClick={(e) => e.stopPropagation()}>
                              <span className="input-group-text"><i className="bi bi-pencil-square"></i></span>
                              <input 
                                type="text" 
                                className="form-control" 
                                id="title"
                                ref={customTitleRef}
                                value={formData.title} 
                                onChange={handleInputChange}
                                placeholder="보고서 제목을 입력하세요"
                                disabled={formData.titleOption !== 'custom'}
                              />
                            </div>
                          </div>
                          <p className="text-muted small">
                            <i className="bi bi-info-circle me-1"></i>
                            원하는 제목을 직접 입력할 수 있습니다.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Section 3 */}
          <section className="swiper-slide analysis-section" id="section3">
            <div className="container">
              <div className="section-content text-center">
                <h1 className="mb-5" data-aos="fade-up">기업 분석 - 3단계</h1>
                <div className="card shadow-lg border-0 p-4" data-aos="fade-up" data-aos-delay="100">
                  <h3>분석 보고서 목차 설정</h3>
                  
                  {/* 목차 선택 영역 (2열 레이아웃으로 변경) */}
                  <div className="mt-4 text-start">
                    <div className="row">
                      {/* 왼쪽 열: 섹션 1-3 */}
                      <div className="col-lg-6">
                        {/* 섹션 1 */}
                        <div className="mb-4">
                          <div className="form-check">
                            <input 
                              className="form-check-input section-checkbox" 
                              type="checkbox" 
                              id="section1Check" 
                              checked={selectedSections.section1}
                              onChange={handleSectionToggle}
                            />
                            <label className="form-check-label fw-bold" htmlFor="section1Check">
                              1. 보고서 요약
                            </label>
                          </div>
                          <div id="section1Subsections" className="ms-4 mt-1">
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section1_1Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section1_1Check">
                                1.1 실적 주요 특징
                              </label>
                            </div>
                            <div className="form-check">
                              <input className="form-check-input" type="checkbox" id="section1_2Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section1_2Check">
                                1.2 향후 전망 핵심
                              </label>
                            </div>
                          </div>
                        </div>
                        
                        {/* 섹션 2 */}
                        <div className="mb-4">
                          <div className="form-check">
                            <input 
                              className="form-check-input section-checkbox" 
                              type="checkbox" 
                              id="section2Check" 
                              checked={selectedSections.section2}
                              onChange={handleSectionToggle}
                            />
                            <label className="form-check-label fw-bold" htmlFor="section2Check">
                              2. 실적 분석
                            </label>
                          </div>
                          <div id="section2Subsections" className="ms-4 mt-1">
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section2_1Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section2_1Check">
                                2.1 주요 재무 결과
                              </label>
                            </div>
                            <div className="form-check">
                              <input className="form-check-input" type="checkbox" id="section2_2Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section2_2Check">
                                2.2 실적 요인 분석
                              </label>
                            </div>
                          </div>
                        </div>

                        {/* 섹션 3 */}
                        <div className="mb-4">
                          <div className="form-check">
                            <input 
                              className="form-check-input section-checkbox" 
                              type="checkbox" 
                              id="section3Check" 
                              checked={selectedSections.section3}
                              onChange={handleSectionToggle}
                            />
                            <label className="form-check-label fw-bold" htmlFor="section3Check">
                              3. 주요 사업 및 제품 동향
                            </label>
                          </div>
                          <div id="section3Subsections" className="ms-4 mt-1">
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section3_1Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section3_1Check">
                                3.1 제품 관련 소식
                              </label>
                            </div>
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section3_2Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section3_2Check">
                                3.2 R&D 및 파이프라인
                              </label>
                            </div>
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section3_3Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section3_3Check">
                                3.3 주요 사업
                              </label>
                            </div>
                            <div className="form-check">
                              <input className="form-check-input" type="checkbox" id="section3_4Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section3_4Check">
                                3.4 기타 사업
                              </label>
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      {/* 오른쪽 열: 섹션 4-5 (섹션 6 제거) */}
                      <div className="col-lg-6">
                        {/* 섹션 4 */}
                        <div className="mb-4">
                          <div className="form-check">
                            <input 
                              className="form-check-input section-checkbox" 
                              type="checkbox" 
                              id="section4Check" 
                              checked={selectedSections.section4}
                              onChange={handleSectionToggle}
                            />
                            <label className="form-check-label fw-bold" htmlFor="section4Check">
                              4. 시장 환경 및 전략 방향
                            </label>
                          </div>
                          <div id="section4Subsections" className="ms-4 mt-1">
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section4_1Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section4_1Check">
                                4.1 주요 시장 활동
                              </label>
                            </div>
                            <div className="form-check">
                              <input className="form-check-input" type="checkbox" id="section4_2Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section4_2Check">
                                4.2 회사의 공식 전략
                              </label>
                            </div>
                          </div>
                        </div>
                        
                        {/* 섹션 5 */}
                        <div className="mb-4">
                          <div className="form-check">
                            <input 
                              className="form-check-input section-checkbox" 
                              type="checkbox" 
                              id="section5Check" 
                              checked={selectedSections.section5}
                              onChange={handleSectionToggle}
                            />
                            <label className="form-check-label fw-bold" htmlFor="section5Check">
                              5. 향후 전망
                            </label>
                          </div>
                          <div id="section5Subsections" className="ms-4 mt-1">
                            <div className="form-check mb-1">
                              <input className="form-check-input" type="checkbox" id="section5_1Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section5_1Check">
                                5.1 회사의 공식 입장/계획
                              </label>
                            </div>
                            <div className="form-check">
                              <input className="form-check-input" type="checkbox" id="section5_2Check" defaultChecked />
                              <label className="form-check-label" htmlFor="section5_2Check">
                                5.2 미래 성과 영향 요인
                              </label>
                            </div>
                          </div>
                        </div>

                        {/* 섹션 6 삭제 - 여기서 제거 */}
                      </div>
                    </div>
                  </div>
                  
                  {/* 버튼 영역 */}
                  <div className="mt-4 d-flex justify-content-center gap-3">
                    <button className="btn btn-outline-primary" onClick={() => selectAllSections(true)}>모든 항목 선택</button>
                    <button className="btn btn-outline-secondary" onClick={() => selectAllSections(false)}>모든 항목 해제</button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Section 4 */}
          <section className="swiper-slide analysis-section" id="section4">
            <div className="container">
              <div className="section-content text-center">
                <h1 className="mb-5" data-aos="fade-up">기업 분석 - 고급 설정</h1>
                <div className="card shadow-lg border-0 p-4" data-aos="fade-up" data-aos-delay="100">
                  <h3>(고급 설정) 관심 지표 설정</h3>

                  {/* 자주 사용되는 경제지표 빠른 선택 섹션 */}
                  <div className="mt-4 mb-3">
                    <h5 className="text-start mb-3">주요 경제지표</h5>
                    <div className="d-flex flex-wrap gap-2">
                      {["PER", "PBR", "EPS", "BPS", "ROE", "ROA", "EBITDA", "EV/EBITDA", "매출액성장률", 
                      "영업이익률", "순이익률", "부채비율", "배당수익률", "FCF", "베타"].map((indicator, index) => (
                        <button key={index} 
                          className={`btn btn-sm ${selectedIndicators.includes(indicator) ? 'btn-primary' : 'btn-outline-primary'} indicator-btn`} 
                          data-indicator={indicator} 
                          onClick={() => toggleIndicator(indicator)}>
                          {indicator}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 검색 기능 */}
                  <div className="mt-4 mb-4">
                    <div className="input-group">
                      <span className="input-group-text"><i className="bi bi-search"></i></span>
                      <input type="text" className="form-control" id="indicatorSearch" placeholder="지표명 검색..." onKeyUp={searchIndicator} />
                      <button className="btn btn-primary" type="button" onClick={searchIndicator}>검색</button>
                    </div>
                  </div>
                  
                  {/* 검색 결과 영역 */}
                  <div className="mt-3 text-start" id="searchResults" style={{ maxHeight: '150px', overflowY: 'auto', display: 'none' }}>
                    <h6 className="mb-2">검색 결과:</h6>
                    <div className="d-flex flex-wrap gap-2" id="searchResultsList">
                      {/* 검색 결과가 여기에 동적으로 추가됨 */}
                    </div>
                  </div>
                  
                  {/* 선택된 지표 표시 영역 */}
                  <div className="mt-4">
                    <h5 className="text-start mb-3">선택된 지표 <span className="badge bg-primary" id="selectedCount">{selectedIndicators.length}</span></h5>
                    <div className="alert alert-info" id="noSelectionAlert" style={{ display: selectedIndicators.length === 0 ? 'block' : 'none' }}>
                      분석에 포함할 지표를 선택해주세요.
                      일반 사용자는 지표 없이 생성하는 것이 좋습니다.
                    </div>
                    <div className="selected-indicators" id="selectedIndicators" style={{ display: selectedIndicators.length === 0 ? 'none' : 'block' }}>
                      {/* 선택된 지표들을 더 컴팩트한 배지 형태로 표시 */}
                      <div className="d-flex flex-wrap gap-2" id="selectedIndicatorsList">
                        {selectedIndicators.map((indicator, index) => (
                          <div key={index} className="badge bg-light text-dark border p-2 d-flex align-items-center" style={{ fontSize: '0.9rem' }}>
                            <span>{indicator}</span>
                            <button type="button" 
                              className="btn-close btn-close-sm ms-2" 
                              style={{ fontSize: '0.7rem' }}
                              onClick={() => removeIndicator(indicator)}
                              aria-label="Close">
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Section 5 */}
          <section className="swiper-slide analysis-section" id="section5">
            <div className="container">
              <div className="section-content text-center">
                <h1 className="mb-5" data-aos="fade-up">기업 분석 - 최종 단계</h1>
                <div className="card shadow-lg border-0 p-4" data-aos="fade-up" data-aos-delay="100">
                  <h3>보고서 생성</h3>
                  
                  {/* 입력 정보 요약 - 가로 길이 2배로 확장 */}
                  <div className="mt-4">
                    <h5 className="text-start mb-3">입력 정보 요약</h5>
                    <div className="card bg-light" style={{ maxWidth: '100%', margin: '0 auto' }}>
                      <div className="card-body">
                        <div className="row">
                          <div className="col-md-6 text-start">
                            <p><strong>기업명:</strong> <span id="summaryCompanyName">-</span></p>
                            <p><strong>분석 기준 분기:</strong> <span id="summaryQuarter">-</span></p>
                            <p><strong>보고서 제목:</strong> <span id="summaryTitle">-</span></p>
                          </div>
                          <div className="col-md-6 text-start">
                            <p><strong>목차 섹션 수:</strong> <span id="summarySections">-</span> 개</p>
                            <p><strong>선택된 지표:</strong> <span id="summaryIndicators">-</span></p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* 오류 메시지 표시 */}
                  {error && (
                    <div className="mt-4 alert alert-danger">
                      <i className="bi bi-exclamation-triangle-fill me-2"></i>
                      {error}
                    </div>
                  )}
                  
                  {/* 보고서 생성 안내 */}
                  <div className="mt-4 alert alert-warning">
                    <i className="bi bi-info-circle-fill me-2"></i> 
                    <strong>보고서 생성에는 1분 이상이 걸릴 수 있습니다.</strong>
                    <p className="mb-0 mt-1">생성이 완료되면 보고서 목록 페이지로 이동합니다.</p>
                  </div>
                  
                  {/* 보고서 생성 버튼 - 가로 크기 증가 */}
                  <div className="mt-4 d-grid gap-2 col-md-8 mx-auto">
                    <button 
                      className="btn btn-primary btn-lg btn-generate-report" 
                      onClick={generateReport}
                      disabled={isGenerating}
                    >
                      {isGenerating ? (
                        <>
                          <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                          보고서 생성 중...
                        </>
                      ) : (
                        <>
                          <i className="bi bi-file-earmark-text me-2"></i> 보고서 생성하기
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
        
        {/* Pagination */}
        <div className="swiper-pagination"></div>
        
        {/* Navigation buttons */}
        <div className="navigation-buttons">
          <div className="navigation-container">
            <div className="d-flex justify-content-between align-items-center">
              <button className="btn btn-primary swiper-button_prev-custom" onClick={prevSlide}>
                <i className="bi bi-arrow-left"></i> 이전
              </button>
              <div className="nav-indicator">
                <span id="current-slide">{currentSlide}</span> / <span id="total-slides">{totalSlides}</span>
              </div>
              <button className="btn btn-primary swiper-button_next-custom" onClick={nextSlide}>
                다음 <i className="bi bi-arrow-right"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
};

export default CompanyAnalysis;
