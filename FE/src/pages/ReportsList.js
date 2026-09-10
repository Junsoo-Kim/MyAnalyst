import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import './ReportsList.css'; // CSS 파일 추가 필요

const ReportsList = () => {
  const [reports, setReports] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

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

    // 사용자 ID 가져오기 및 API에서 보고서 데이터 가져오기
    const fetchReports = async () => {
      const userId = getUserIdFromCookie();
      
      // 로그인 상태가 아니면 로그인 페이지로 리다이렉트
      if (!userId) {
        navigate('/login');
        return;
      }
      
      try {
        setIsLoading(true);
        const response = await apiFetch(`/reports/user/${userId}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include', // 쿠키 포함
        });

        if (!response.ok) {
          throw new Error('보고서를 불러오는데 실패했습니다.');
        }

        const data = await response.json();
        
        // API 응답 데이터를 UI에 맞게 가공
        const formattedReports = data.map(report => ({
          id: report.reportid,
          title: report.title,
          date: new Date().toLocaleDateString('ko-KR', { // 날짜 정보가 없으므로 현재 날짜로 대체
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
          }).replace(/\. /g, '.'),
          isRecent: report.reportid === Math.max(...data.map(r => r.reportid)) // 가장 높은 reportid를 최근 항목으로 표시
        }));
        
        setReports(formattedReports);
      } catch (err) {
        console.error('보고서 불러오기 오류:', err);
        setError('보고서 목록을 불러오는 중 오류가 발생했습니다.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchReports();
  }, [navigate]);

  return (
    <main id="main">
      {/* 보고서 목록 섹션 */}
      <section id="reports-list" className="reports-list-section">
        <div className="hero-img"></div>
        
        <div className="container reports-list-container">
          <div className="row">
            <div className="col-lg-10 mx-auto">
              <div className="reports-list" data-aos="fade-up">
                <h1 className="page-title" style={{backgroundColor:'transparent'}}>내 보고서 목록</h1>
                
                {/* 로딩 상태 표시 */}
                {isLoading ? (
                  <div className="text-center p-5">
                    <div className="spinner-border" role="status">
                      <span className="visually-hidden">Loading...</span>
                    </div>
                    <p className="mt-3">보고서 목록을 불러오는 중입니다...</p>
                  </div>
                ) : error ? (
                  <div className="alert alert-danger" role="alert">
                    {error}
                  </div>
                ) : reports.length === 0 ? (
                  <div className="alert alert-info" role="alert">
                    생성된 보고서가 없습니다.
                  </div>
                ) : (
                  /* 보고서 목록 */
                  <div className="reports-items">
                    {reports.map(report => (
                      <div className="report-item" key={report.id}>
                        <Link to={`/report-view?id=${report.id}`}>
                          <div className="d-flex justify-content-between align-items-center">
                            <div>
                              {report.title}
                              {report.isRecent && <span className="badge bg-primary ms-2">최근</span>}
                            </div>
                            <div className="date">{report.date}</div>
                          </div>
                        </Link>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};

export default ReportsList;
