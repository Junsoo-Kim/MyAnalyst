import React, { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { marked } from 'marked';
import { apiFetch, apiUrl } from '../api/client';
import ReportSidebar from '../components/ReportSidebar';
import { sanitizeReportHtml } from '../utils/sanitizeReportHtml';
import './ReportView.css';

const ReportView = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const reportId = queryParams.get('id');

  const [report, setReport] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [headings, setHeadings] = useState([]);
  const [showSidebar, setShowSidebar] = useState(false);
  // 뉴스 데이터를 저장할 상태 추가
  const [news, setNews] = useState([]);
  const [isNewsLoading, setIsNewsLoading] = useState(false);
  
  // 주식 정보 관련 상태 추가
  const [stockInfo, setStockInfo] = useState(null);
  const [isStockLoading, setIsStockLoading] = useState(false);
  const [stockChartUrl, setStockChartUrl] = useState(null);
  
  // 용어사전 관련 상태 추가
  const [dictionary, setDictionary] = useState([]);
  const [isDictionaryLoading, setIsDictionaryLoading] = useState(false);
  const [expandedTerms, setExpandedTerms] = useState({});
  
  // 사이드바 콘텐츠 타입 상태 - 기본값을 'dictionary'으로 변경
  const [sidebarContentType, setSidebarContentType] = useState('dictionary');
  
  // 헤더 숨김 관련 상태
  const [isHeaderHidden, setIsHeaderHidden] = useState(false);
  const lastScrollTop = useRef(0);
  const headerRef = useRef(null);
  const sidebarRef = useRef(null);

  // 스크롤 이벤트 핸들러
  useEffect(() => {
    // 스크롤 이벤트 핸들러
    const handleScroll = () => {
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      const threshold = 70;

      if (scrollTop > lastScrollTop.current && scrollTop > threshold) {
        // 아래로 스크롤 - 헤더 숨기기
        setIsHeaderHidden(true);
      } else if (scrollTop < lastScrollTop.current || scrollTop <= threshold) {
        // 위로 스크롤 또는 맨 위 부분 - 헤더 표시
        setIsHeaderHidden(false);
      }
      
      lastScrollTop.current = scrollTop <= 0 ? 0 : scrollTop;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    // 보고서 ID가 없으면 목록 페이지로 이동
    if (!reportId) {
      navigate('/reports-list');
      return;
    }

    const fetchReport = async () => {
      try {
        setIsLoading(true);
        setError(null);

        const response = await apiFetch(`/reports/${reportId}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json'
          },
          credentials: 'include' // 쿠키 포함
        });

        if (!response.ok) {
          throw new Error('보고서를 불러오는데 실패했습니다.');
        }

        const data = await response.json();

        // API 응답 데이터를 UI에 맞게 가공
        const formattedReport = {
          id: reportId,
          title: data.title,
          company: data.company, // 회사명 필드 추가
          date: data.date || new Date().toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
          }).replace(/\. /g, '년 ') + '일',
          content: processContent(data.content)
        };
        
        setReport(formattedReport);
        
        // 목차 생성
        const extractedHeadings = processChapters(data.chapter);
        setHeadings(extractedHeadings);

        // API에서 받은 company 필드를 사용하여 뉴스 데이터 및 주식 정보를 가져옴
        if (data.company) {
          fetchNewsForCompany(data.company);
          fetchStockInfo(data.company);
        }
        
        // 용어 사전 데이터 가져오기
        fetchDictionary(reportId);
      } catch (err) {
        console.error('보고서 불러오기 오류:', err);
        setError('보고서를 불러오는 중 오류가 발생했습니다.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchReport();
  }, [reportId, navigate]);

  // 회사 뉴스 데이터 가져오기 함수
  const fetchNewsForCompany = async (companyName) => {
    try {
      setIsNewsLoading(true);
      const response = await apiFetch(`/news/${companyName}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include'
      });

      if (!response.ok) {
        console.error('뉴스 데이터를 불러오는데 실패했습니다.');
        return;
      }

      const newsData = await response.json();
      setNews(newsData);
    } catch (err) {
      console.error('뉴스 데이터 불러오기 오류:', err);
    } finally {
      setIsNewsLoading(false);
    }
  };
  
  // 주식 정보 가져오기 함수
  const fetchStockInfo = async (companyName) => {
    try {
      setIsStockLoading(true);
      const response = await apiFetch(`/stocks/${companyName}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include'
      });

      if (!response.ok) {
        console.error('주식 정보를 불러오는데 실패했습니다.');
        return;
      }

      const stockData = await response.json();
      setStockInfo(stockData);
      
      // 차트 이미지 URL 설정
      setStockChartUrl(apiUrl(`/stocks/${companyName}/chart-image`));
    } catch (err) {
      console.error('주식 정보 불러오기 오류:', err);
    } finally {
      setIsStockLoading(false);
    }
  };

  // 용어 사전 데이터 가져오기 함수
  const fetchDictionary = async (reportId) => {
    try {
      setIsDictionaryLoading(true);
      const response = await apiFetch(`/reports/${reportId}/dictionary`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include'
      });

      if (!response.ok) {
        console.error('용어 사전 데이터를 불러오는데 실패했습니다.');
        return;
      }

      const dictionaryData = await response.json();
      setDictionary(dictionaryData);
    } catch (err) {
      console.error('용어 사전 불러오기 오류:', err);
    } finally {
      setIsDictionaryLoading(false);
    }
  };

  // 용어 확장/축소 토글 함수
  const toggleTermExpansion = (term) => {
    setExpandedTerms(prev => ({
      ...prev,
      [term]: !prev[term]
    }));
  };

  // 사이드바 컨텐츠 타입 변경 함수
  const changeSidebarContent = (contentType) => {
    setSidebarContentType(contentType);
  };

  // 목차 텍스트에서 섹션과 서브섹션 추출하는 함수
  const processChapters = (chapterText) => {
    if (!chapterText) return [];
    
    const lines = chapterText.split('\n').filter(line => line.trim() !== '');
    const headingsStructure = [];
    let currentMainHeading = null;
    
    lines.forEach(line => {
      const trimmedLine = line.trim();
      
      // 1, 2와 같은 메인 섹션 구분
      if (/^\d+\./.test(trimmedLine) && !trimmedLine.includes(' ')) {
        const sectionId = `section${trimmedLine.replace('.', '')}`;
        currentMainHeading = {
          id: sectionId,
          text: trimmedLine,
          level: 1,
          children: []
        };
        headingsStructure.push(currentMainHeading);
      }
      // 1.1, 2.1과 같은 서브섹션 구분
      else if (/^\d+\.\d+/.test(trimmedLine) && currentMainHeading) {
        const subSectionMatch = trimmedLine.match(/^(\d+\.\d+)\s+(.*)/);
        if (subSectionMatch) {
          const number = subSectionMatch[1];
          const title = subSectionMatch[2];
          const mainNumber = number.split('.')[0];
          const subNumber = number.split('.')[1];
          const sectionId = `section${mainNumber}-${subNumber}`;
          
          currentMainHeading.children.push({
            id: sectionId,
            text: `${number} ${title}`,
            level: 2
          });
        } else {
          // 서브섹션 번호만 있는 경우
          const mainSubMatch = trimmedLine.match(/^(\d+\.\d+)/);
          if (mainSubMatch) {
            const number = mainSubMatch[1];
            const mainNumber = number.split('.')[0];
            const subNumber = number.split('.')[1];
            const sectionId = `section${mainNumber}-${subNumber}`;
            
            currentMainHeading.children.push({
              id: sectionId,
              text: trimmedLine,
              level: 2
            });
          }
        }
      }
    });
    
    return headingsStructure;
  };

  // 마크다운 콘텐츠에 섹션 ID 추가 - 중복 헤딩 방지 개선
  const processContent = (content) => {
    if (!content) return '';
    
    let processedContent = content;
    const processedHeadings = new Set(); // 이미 처리된 헤딩을 추적
    
    // 각 라인별로 처리하여 중복 헤딩 방지
    const lines = processedContent.split('\n');
    const processedLines = lines.map(line => {
      // 이미 처리된 라인은 그대로 반환
      if (line.includes('<span id="section')) {
        return line;
      }
      
      // 패턴 1: ### 1. 보고서 요약 형태
      const pattern1 = /^(#{1,3})\s+(\d+\.)\s+([^\n]+)$/;
      if (pattern1.test(line)) {
        const match = line.match(pattern1);
        const [, hashes, number, title] = match;
        const sectionNumber = number.replace('.', '');
        const headingKey = `section${sectionNumber}`;
        
        // 이미 처리된 헤딩인지 확인
        if (processedHeadings.has(headingKey)) {
          return line; // 이미 처리됐다면 원본 그대로 반환
        }
        
        processedHeadings.add(headingKey);
        return `${hashes} <span id="${headingKey}">${number} ${title}</span>`;
      }
      
      // 패턴 2: ### 1.1 실적 요인 분석 형태
      const pattern2 = /^(#{1,3})\s+(\d+\.\d+)\s+([^\n]+)$/;
      if (pattern2.test(line)) {
        const match = line.match(pattern2);
        const [, hashes, number, title] = match;
        const [mainNumber, subNumber] = number.split('.');
        const sectionId = `section${mainNumber}-${subNumber}`;
        
        // 이미 처리된 헤딩인지 확인
        if (processedHeadings.has(sectionId)) {
          return line; // 이미 처리됐다면 원본 그대로 반환
        }
        
        processedHeadings.add(sectionId);
        return `${hashes} <span id="${sectionId}">${number} ${title}</span>`;
      }
      
      // 패턴 3: 숫자로만 시작하는 경우 (##없이): 1. 보고서 요약
      const pattern3 = /^(\d+\.)\s+([^\n]+)$/;
      if (pattern3.test(line)) {
        const match = line.match(pattern3);
        const [, number, title] = match;
        const sectionNumber = number.replace('.', '');
        const headingKey = `section${sectionNumber}`;
        
        // 이미 처리된 헤딩인지 확인
        if (processedHeadings.has(headingKey)) {
          return line; // 이미 처리됐다면 원본 그대로 반환
        }
        
        processedHeadings.add(headingKey);
        return `### <span id="${headingKey}">${number} ${title}</span>`;
      }
      
      // 패턴 4: 숫자.숫자로 시작하는 경우 (##없이): 1.1 실적 요인 분석
      const pattern4 = /^(\d+\.\d+)\s+([^\n]+)$/;
      if (pattern4.test(line)) {
        const match = line.match(pattern4);
        const [, number, title] = match;
        const [mainNumber, subNumber] = number.split('.');
        const sectionId = `section${mainNumber}-${subNumber}`;
        
        // 이미 처리된 헤딩인지 확인
        if (processedHeadings.has(sectionId)) {
          return line; // 이미 처리됐다면 원본 그대로 반환
        }
        
        processedHeadings.add(sectionId);
        return `#### <span id="${sectionId}">${number} ${title}</span>`;
      }
      
      return line; // 패턴에 맞지 않는 경우 원본 그대로 반환
    });
    
    return processedLines.join('\n');
  };
  
  // HTML 컨텐츠에서 용어 하이라이팅
  const highlightTermsInContent = (htmlContent) => {
    if (!dictionary || dictionary.length === 0 || !htmlContent) {
      return htmlContent;
    }

    // 용어를 길이 기준 내림차순으로 정렬 (긴 용어 먼저 처리)
    const sortedTerms = [...dictionary].sort((a, b) => 
      b.term.length - a.term.length
    );
    
    // HTML 문자열 기반 접근 방식으로 변경
    let processedHTML = htmlContent;
    
    // 용어 정규식 이스케이프 함수
    const escapeRegExp = (string) => {
      return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    };
    
    // 각 용어에 대해 하이라이팅 처리
    sortedTerms.forEach(item => {
      const term = item.term;
      const escapedTerm = escapeRegExp(term);
      
      // lookbehind와 lookahead를 사용하여 단어 경계 조건 처리
      // (?<!(>|[a-zA-Z가-힣])) - 앞에 태그 닫기(>)나 문자가 오지 않음
      // (?!(>|[a-zA-Z가-힣])) - 뒤에 태그 열기(<)나 문자가 오지 않음
      const regex = new RegExp(
        `(?<!(<|[a-zA-Z가-힣]))${escapedTerm}(?!(>|[a-zA-Z가-힣]))`, 
        'g'
      );
      
      // 하이라이트 처리된 HTML로 교체
      processedHTML = processedHTML.replace(
        regex, 
        `<span class="highlighted-term" data-term="${term}">${term}</span>`
      );
    });
    
    return processedHTML;
  };

  // 하이라이트된 용어에 이벤트 핸들러 추가
  useEffect(() => {
    if (!isLoading && dictionary.length > 0) {
      // DOM이 완전히 로드된 후 실행
      setTimeout(() => {
        const contentElement = document.getElementById('markdownContent');
        if (contentElement) {
          // 이전에 추가된 이벤트 리스너 제거
          const oldTermElements = contentElement.querySelectorAll('.highlighted-term');
          oldTermElements.forEach(el => {
            el.removeEventListener('click', el.__termClickHandler);
          });
          
          // 새 이벤트 리스너 추가
          const termElements = contentElement.querySelectorAll('.highlighted-term');
          
          termElements.forEach(element => {
            // 함수를 저장하여 나중에 제거할 수 있도록 함
            const handler = () => {
              const term = element.getAttribute('data-term');
              
              // 모바일에서는 사이드바 표시
              if (window.innerWidth < 992) {
                setShowSidebar(true);
              }
              
              // 사이드바에서 사전 탭으로 전환
              setSidebarContentType('dictionary');
              
              // 해당 용어의 설명 펼치기 또는 접기 토글
              setExpandedTerms(prev => ({
                ...prev,
                [term]: !prev[term]
              }));
              
              // 사이드바에서 해당 용어로 스크롤
              setTimeout(() => {
                const termElement = document.querySelector(`.dictionary-item .term-text[data-term="${term}"]`);
                if (termElement && termElement.closest('.dictionary-item')) {
                  termElement.closest('.dictionary-item').scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'center' 
                  });
                }
              }, 200);
            };
            
            element.__termClickHandler = handler; // 함수 레퍼런스 저장
            element.addEventListener('click', handler);
          });
          
          console.log(`Highlighted ${termElements.length} terms in the report`);
        }
      }, 500); // DOM이 완전히 로드되도록 지연 실행
    }
  }, [isLoading, dictionary, showSidebar, setSidebarContentType, setExpandedTerms]);

  // 목차 항목 클릭 시 스크롤 이동 함수
  const scrollToSection = (event, sectionId) => {
    event.preventDefault();
    const targetElement = document.getElementById(sectionId);
    
    if (targetElement) {
      window.scrollTo({
        top: targetElement.offsetTop - 100,
        behavior: 'smooth'
      });
      
      // 모바일에서는 사이드바 닫기
      if (window.innerWidth < 992) {
        setShowSidebar(false);
      }
    }
  };

  return (
    <>      
      <div className="report-container">
        {/* 메인 콘텐츠 영역 (보고서) */}
        <div className="main-content">
          {isLoading ? (
            <div className="text-center p-5">
              <div className="spinner-border" role="status">
                <span className="visually-hidden">Loading...</span>
              </div>
              <p className="mt-3">보고서를 불러오는 중입니다...</p>
            </div>
          ) : error ? (
            <div className="alert alert-danger m-5" role="alert">
              <h4 className="alert-heading">오류 발생</h4>
              <p>{error}</p>
              <hr />
              <p className="mb-0">
                <button 
                  className="btn btn-outline-danger" 
                  onClick={() => navigate('/reports-list')}
                >
                  보고서 목록으로 돌아가기
                </button>
              </p>
            </div>
          ) : (
            <>
              <div className="report-tools">
                <div className="d-flex align-items-center">
                  <h1>
                    <span id="reportTitle">{report.title}</span>
                    <span className="report-date"> - {report.date}</span>
                  </h1>
                </div>
              </div>
              
              <div 
                id="markdownContent" 
                className="markdown-content"
                dangerouslySetInnerHTML={{ 
                  __html: sanitizeReportHtml(highlightTermsInContent(marked.parse(report.content)))
                }}
              />
            </>
          )}
        </div>
        
        {/* 우측 사이드바 (목차 제거, 나머지 기능 유지) */}
        <ReportSidebar
          isHeaderHidden={isHeaderHidden}
          showSidebar={showSidebar}
          sidebarContentType={sidebarContentType}
          changeSidebarContent={changeSidebarContent}
          // headings와 scrollToSection은 더 이상 필요없지만 호환성을 위해 유지
          headings={headings}
          scrollToSection={scrollToSection}
          news={news}
          isNewsLoading={isNewsLoading}
          dictionary={dictionary}
          isDictionaryLoading={isDictionaryLoading}
          expandedTerms={expandedTerms}
          toggleTermExpansion={toggleTermExpansion}
          stockInfo={stockInfo}
          isStockLoading={isStockLoading}
          stockChartUrl={stockChartUrl}
          sidebarRef={sidebarRef}
          reportId={reportId}
        />
      </div>
    </>
  );
};

export default ReportView;
