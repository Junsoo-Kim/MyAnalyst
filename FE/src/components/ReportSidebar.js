import React, { useState, useEffect, useRef } from 'react';
import { apiFetch } from '../api/client';

const ReportSidebar = ({
  isHeaderHidden,
  showSidebar,
  sidebarContentType,
  changeSidebarContent,
  // headings와 scrollToSection은 더 이상 필요없지만 호환성을 위해 남겨둠
  headings,
  scrollToSection,
  news,
  isNewsLoading,
  dictionary,
  isDictionaryLoading,
  expandedTerms,
  toggleTermExpansion,
  stockInfo,
  isStockLoading,
  stockChartUrl,
  sidebarRef,
  reportId // Add reportId prop
}) => {
  // 채팅 상태 관리
  const [chatMessages, setChatMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isChatHistoryLoading, setIsChatHistoryLoading] = useState(false);
  const chatEndRef = useRef(null);
  const inputRef = useRef(null); // 입력창에 대한 ref

  // 음성 녹음 관련 상태 추가
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordingError, setRecordingError] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordingTimerRef = useRef(null);

  // 채팅 기록 로딩
  useEffect(() => {
    if (reportId && sidebarContentType === 'chat') {
      fetchChatHistory(reportId);
    }
  }, [reportId, sidebarContentType]);

  // 채팅 기록 가져오기 함수
  const fetchChatHistory = async (reportId) => {
    setIsChatHistoryLoading(true);
    try {
      const response = await apiFetch(`/reports/${reportId}/chat`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include'
      });

      if (response.ok) {
        const chatHistory = await response.json();
        
        // 채팅 기록을 메시지 형식으로 변환
        const formattedMessages = chatHistory.flatMap(chat => [
          {
            id: `user-${chat.chatid}`,
            type: 'user',
            text: chat.question
          },
          {
            id: `bot-${chat.chatid}`,
            type: 'bot',
            text: chat.answer
          }
        ]);

        // 채팅 메시지 설정
        setChatMessages(formattedMessages);
      } else {
        console.error('채팅 기록을 가져오는데 실패했습니다.');
      }
    } catch (error) {
      console.error('채팅 기록 로딩 오류:', error);
    } finally {
      setIsChatHistoryLoading(false);
    }
  };

  // 채팅 메시지가 추가될 때 자동 스크롤
  useEffect(() => {
    if (chatEndRef.current && sidebarContentType === 'chat') {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, sidebarContentType]);

  // 녹음 기능 시작
  const startRecording = async () => {
    setRecordingError(null);
    audioChunksRef.current = [];
    
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      
      mediaRecorderRef.current.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      });
      
      mediaRecorderRef.current.addEventListener("stop", () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setAudioBlob(audioBlob);
        
        // 녹음이 끝나면 서버로 전송
        handleAudioUpload(audioBlob);

        // 스트림 트랙들 중지
        stream.getTracks().forEach(track => track.stop());
      });
      
      // 녹음 시작
      mediaRecorderRef.current.start();
      setIsRecording(true);
      
      // 녹음 시간 타이머 시작
      setRecordingTime(0);
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
      
    } catch (error) {
      console.error("음성 녹음 시작 오류:", error);
      setRecordingError("마이크 액세스를 허용해 주세요.");
    }
  };
  
  // 녹음 중지
  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      
      // 타이머 정지
      clearInterval(recordingTimerRef.current);
    }
  };
  
  // 오디오 파일 업로드 처리
  const handleAudioUpload = async (audioBlob) => {
    if (!audioBlob) return;
    
    setIsChatLoading(true);
    
    try {
      const formData = new FormData();
      formData.append('reportid', reportId);
      formData.append('audio_file', audioBlob, 'voice_question.webm');
      
      // 로딩 상태 및 임시 메시지 추가
      const tempUserMessage = {
        id: Date.now(),
        type: 'user',
        text: "음성 메시지 처리 중..." // 처리 중인 상태를 표시
      };
      
      setChatMessages(prev => [...prev, tempUserMessage]);
      
      const response = await apiFetch('/chat/stt', {
        method: 'POST',
        credentials: 'include',
        body: formData
      });
      
      if (!response.ok) {
        throw new Error('음성 처리 요청에 실패했습니다.');
      }
      
      const data = await response.json();
      
      // 현재 메시지 목록 가져오기
      let currentMessages = [...chatMessages];
      
      // 임시 메시지 찾기 및 실제 텍스트로 교체
      const tempMessageIndex = currentMessages.findIndex(
        msg => msg.id === tempUserMessage.id
      );
      
      if (tempMessageIndex !== -1) {
        // 임시 메시지를 실제 텍스트로 교체
        currentMessages[tempMessageIndex] = {
          ...currentMessages[tempMessageIndex],
          text: data.question || "음성 질문을 처리할 수 없습니다."
        };
        
        // 상태 업데이트
        setChatMessages(currentMessages);
        
        // 음성 질문에 대한 AI 답변 추가
        const botMessage = {
          id: Date.now() + 1,
          type: 'bot',
          text: data.answer
        };
        
        setChatMessages(prev => [...prev, botMessage]);
      }
      
    } catch (error) {
      console.error("음성 질문 처리 오류:", error);
      
      const errorMessage = {
        id: Date.now() + 1,
        type: 'error',
        text: '음성 인식 처리 중 오류가 발생했습니다. 다시 시도해주세요.'
      };
      
      setChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsChatLoading(false);
      setAudioBlob(null); // 음성 블롭 초기화
    }
  };
  
  // 녹음 시간 포맷팅
  const formatRecordingTime = (seconds) => {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  };

  // 컴포넌트 언마운트 시 녹음 정리
  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
      if (mediaRecorderRef.current && isRecording) {
        mediaRecorderRef.current.stop();
        setIsRecording(false);
      }
    };
  }, [isRecording]);

  // 채팅 컴포넌트
  const ChatComponent = () => {
    // 기본 상태 관리
    const [localInput, setLocalInput] = useState('');
    
    // 채팅 탭이 선택되면 자동으로 입력창에 포커스
    useEffect(() => {
      if (sidebarContentType === 'chat' && inputRef.current) {
        inputRef.current.focus();
      }
    }, [sidebarContentType]);

    // 기본 HTML input 방식의 폼 제출 핸들러
    const handleFormSubmit = (e) => {
      e.preventDefault();
      
      if (!localInput.trim()) return;
      
      // 사용자 메시지 생성 및 추가
      const userMessage = {
        id: Date.now(),
        type: 'user',
        text: localInput
      };
      
      // 채팅 메시지에 추가
      setChatMessages(prev => [...prev, userMessage]);
      
      // 입력창 초기화
      setLocalInput('');
      
      // 로딩 상태 설정
      setIsChatLoading(true);
      
      // API 호출
      apiFetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          reportid: reportId,
          question: userMessage.text
        })
      })
      .then(response => {
        if (!response.ok) {
          throw new Error('채팅 응답을 받지 못했습니다.');
        }
        return response.json();
      })
      .then(data => {
        // 봇 응답 추가
        const botMessage = {
          id: Date.now() + 1,
          type: 'bot',
          text: data.answer
        };
        
        setChatMessages(prev => [...prev, botMessage]);
      })
      .catch(error => {
        console.error('채팅 에러:', error);
        
        // 에러 메시지 추가
        const errorMessage = {
          id: Date.now() + 1,
          type: 'error',
          text: '죄송합니다. 질문에 대한 답변을 가져오는 중 오류가 발생했습니다.'
        };
        
        setChatMessages(prev => [...prev, errorMessage]);
      })
      .finally(() => {
        setIsChatLoading(false);
        
        // 입력창에 포커스
        if (inputRef.current) {
          inputRef.current.focus();
        }
      });
    };

    return (
      <div className="chat-container">
        <h4>나만의 금융 전문가</h4>
        <p className="chat-description">금융 전문가에게 보고서 내용에 대해 질문하세요</p>
        
        <div className="chat-messages">
          {isChatHistoryLoading ? (
            <div className="chat-loading text-center p-3">
              <div className="spinner-border spinner-border-sm" role="status">
                <span className="visually-hidden">Loading...</span>
              </div>
              <p className="mt-2 small">이전 대화 내용을 불러오는 중...</p>
            </div>
          ) : chatMessages.length === 0 ? (
            <div className="chat-welcome">
              <p>안녕하세요! 보고서에 대해 궁금한 점이 있으면 질문해주세요.</p>
              <p>예시 질문:</p>
              <ul>
                <li onClick={() => setLocalInput("이 회사의 주요 경쟁력은 무엇인가요?")}>이 회사의 주요 경쟁력은 무엇인가요?</li>
                <li onClick={() => setLocalInput("향후 성장 전략에 대해 설명해주세요.")}>향후 성장 전략에 대해 설명해주세요.</li>
                <li onClick={() => setLocalInput("재무 상황은 어떤가요?")}>재무 상황은 어떤가요?</li>
              </ul>
            </div>
          ) : (
            chatMessages.map(msg => (
              <div 
                key={msg.id} 
                className={`chat-message ${msg.type === 'user' ? 'user-message' : msg.type === 'error' ? 'error-message' : 'bot-message'}`}
              >
                {msg.type === 'user' ? (
                  <div className="message-header user-header">나</div>
                ) : msg.type === 'error' ? (
                  <div className="message-header error-header">오류</div>
                ) : (
                  <div className="message-header bot-header">금융 전문가</div>
                )}
                <div className="message-bubble">
                  {msg.text.split('\n').map((line, i) => (
                    <React.Fragment key={i}>
                      {line}
                      {i < msg.text.split('\n').length - 1 && <br />}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            ))
          )}
          {isChatLoading && (
            <div className="chat-message bot-message">
              <div className="message-header bot-header">AI 어시스턴트</div>
              <div className="message-bubble typing">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef}></div>
        </div>
        
        {/* 새 대화 시작 버튼 제거 */}
        
        {/* 단순한 HTML form 사용하여 리액트 상태 관리 최소화 */}
        <form className="chat-input-form" onSubmit={handleFormSubmit}>
          <div className="input-group">
            <input
              ref={inputRef}
              type="text"
              className="form-control"
              placeholder="질문을 입력하세요..."
              value={localInput}
              onChange={(e) => setLocalInput(e.target.value)}
              disabled={isChatLoading || isRecording}
            />
            
            {/* 음성 녹음 버튼 추가 */}
            <button 
              type="button" 
              className={`btn ${isRecording ? 'btn-danger' : 'btn-outline-secondary'}`}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isChatLoading}
              title={isRecording ? "녹음 중지" : "음성으로 질문하기"}
            >
              {isRecording ? (
                <span className="d-flex align-items-center">
                  <i className="bi bi-record-fill me-1"></i>
                  <small>{formatRecordingTime(recordingTime)}</small>
                </span>
              ) : (
                <i className="bi bi-mic"></i>
              )}
            </button>
            
            <button 
              type="submit" 
              className="btn btn-primary"
              disabled={!localInput.trim() || isChatLoading || isRecording}
            >
              {isChatLoading ? (
                <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" className="bi bi-send" viewBox="0 0 16 16">
                  <path d="M15.964.686a.5.5 0 0 0-.65-.65L.767 5.855H.766l-.452.18a.5.5 0 0 0-.082.887l.41.26.001.002 4.995 3.178 3.178 4.995.002.002.26.41a.5.5 0 0 0 .886-.083l6-15Zm-1.833 1.89L6.637 10.07l-.215-.338a.5.5 0 0 0-.154-.154l-.338-.215 7.494-7.494 1.178-.471-.47 1.178Z"/>
                </svg>
              )}
            </button>
          </div>
          
          {/* 녹음 오류 메시지 표시 */}
          {recordingError && (
            <div className="text-danger small mt-1">
              <i className="bi bi-exclamation-triangle-fill me-1"></i>
              {recordingError}
            </div>
          )}
        </form>
      </div>
    );
  };

  // 메시지 제출 핸들러
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!inputMessage.trim()) return;
    
    const userMessage = {
      id: Date.now(),
      type: 'user',
      text: inputMessage
    };
    
    setChatMessages(prev => [...prev, userMessage]);
    setInputMessage('');  // 입력창 초기화
    setIsChatLoading(true);
    
    try {
      const response = await apiFetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          reportid: reportId,
          question: userMessage.text
        })
      });
      
      if (!response.ok) {
        throw new Error('채팅 응답을 받지 못했습니다.');
      }
      
      const data = await response.json();
      
      const botMessage = {
        id: Date.now() + 1,
        type: 'bot',
        text: data.answer
      };
      
      setChatMessages(prev => [...prev, botMessage]);
    } catch (error) {
      console.error('채팅 에러:', error);
      
      const errorMessage = {
        id: Date.now() + 1,
        type: 'error',
        text: '죄송합니다. 질문에 대한 답변을 가져오는 중 오류가 발생했습니다.'
      };
      
      setChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsChatLoading(false);
      
      // 응답 완료 후 입력창에 다시 포커스
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }
  };
  
  // 뉴스 컴포넌트
  const CompanyNews = ({ news, isLoading }) => {
    if (isLoading) {
      return (
        <div className="text-center p-3">
          <div className="spinner-border spinner-border-sm" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
          <p className="mt-2 small">뉴스를 불러오는 중...</p>
        </div>
      );
    }

    if (!news || news.length === 0) {
      return (
        <div className="news-empty text-center p-3">
          <p className="text-muted">관련 뉴스가 없습니다.</p>
        </div>
      );
    }

    return (
      <div className="company-news">
        <h4>관련 뉴스</h4>
        <div className="news-list">
          {news.map((item, index) => (
            <div className="news-item" key={index}>
              <h5 className="news-title">
                <a href={item.link} target="_blank" rel="noopener noreferrer">
                  {item.title}
                  {item.press && <span className="news-press"> - {item.press}</span>}
                </a>
              </h5>
              <p className="news-summary">{item.summary}</p>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // 용어 사전 컴포넌트
  const DictionaryComponent = ({ dictionary, isLoading, expandedTerms, onToggleTerm }) => {
    if (isLoading) {
      return (
        <div className="text-center p-3">
          <div className="spinner-border spinner-border-sm" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
          <p className="mt-2 small">용어 사전을 불러오는 중...</p>
        </div>
      );
    }

    if (!dictionary || dictionary.length === 0) {
      return (
        <div className="dictionary-empty text-center p-3">
          <p className="text-muted">용어 사전 정보가 없습니다.</p>
        </div>
      );
    }

    return (
      <div className="dictionary-container">
        <h4>용어 사전</h4>
        <p className="dictionary-description">보고서에 사용된 전문 용어 설명입니다.</p>
        <div className="dictionary-list">
          {dictionary.map((item, index) => (
            <div 
              className={`dictionary-item ${expandedTerms[item.term] ? 'expanded' : ''}`} 
              key={index} 
              id={`dict-term-${item.term.replace(/\s+/g, '-')}`}
            >
              <div 
                className={`dictionary-term ${expandedTerms[item.term] ? 'expanded' : ''}`}
                onClick={() => onToggleTerm(item.term)}
              >
                <span className="term-text" data-term={item.term}>{item.term}</span>
                <span className={`term-icon ${expandedTerms[item.term] ? 'expanded' : ''}`}>
                  {expandedTerms[item.term] ? '−' : '+'}
                </span>
              </div>
              {expandedTerms[item.term] && (
                <div className="dictionary-explanation">
                  {item.explanation}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // 주식 정보 컴포넌트
  const StockInfo = ({ stockInfo, isLoading, chartUrl }) => {
    if (isLoading) {
      return (
        <div className="text-center p-3">
          <div className="spinner-border spinner-border-sm" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
          <p className="mt-2 small">주식 정보를 불러오는 중...</p>
        </div>
      );
    }

    if (!stockInfo) {
      return (
        <div className="stock-empty text-center p-3">
          <p className="text-muted">주식 정보가 없습니다.</p>
        </div>
      );
    }

    return (
      <div className="stock-info">
        <h4>{stockInfo.company_name} 주식 정보</h4>
        <p className="stock-timestamp">{stockInfo.data_timestamp_info}</p>

        <div className="stock-price-section">
          <div className="current-price">
            <span className="price">{stockInfo.current_price}원</span>
            <span className={`change ${parseFloat(stockInfo.change_rate) >= 0 ? 'up' : 'down'}`}>
              {parseFloat(stockInfo.change_rate) >= 0 ? '+' : ''}{stockInfo.change_rate} ({stockInfo.price_change})
            </span>
          </div>
        </div>

        {/* 차트 이미지 추가 */}
        {chartUrl && (
          <div className="stock-chart-container">
            <img 
              src={chartUrl} 
              alt={`${stockInfo.company_name} 주가 차트`} 
              className="stock-chart-image"
              onError={(e) => {
                e.target.onerror = null;
                e.target.style.display = 'none';
                // 에러 발생 시 대체 메시지 표시
                const errorMessage = document.createElement('p');
                errorMessage.className = 'chart-error text-muted text-center';
                errorMessage.textContent = '차트 이미지를 불러올 수 없습니다.';
                e.target.parentNode.appendChild(errorMessage);
              }}
            />
          </div>
        )}

        <table className="stock-data-table">
          <tbody>
            <tr>
              <th>종목코드</th>
              <td>{stockInfo.stock_code}</td>
              <th>시장</th>
              <td>{stockInfo.market_type}</td>
            </tr>
            <tr>
              <th>시가</th>
              <td>{stockInfo.open_price?.replace(/(\d+)\1+$/, '$1')}</td>
              <th>종가</th>
              <td>{stockInfo.yesterday_close?.replace(/(\d+)\1+$/, '$1')}</td>
            </tr>
            <tr>
              <th>고가</th>
              <td>{stockInfo.high_price?.replace(/(\d+)\1+$/, '$1')}</td>
              <th>저가</th>
              <td>{stockInfo.low_price?.replace(/(\d+)\1+$/, '$1')}</td>
            </tr>
            <tr>
              <th>거래량</th>
              <td>{Number(stockInfo.volume?.replace(/(\d+)\1+$/, '$1')).toLocaleString()}</td>
              <th>거래대금</th>
              <td>{stockInfo.volume_value?.replace(/(\d+)\1+$/, '$1')}</td>
            </tr>
            <tr>
              <th>시가총액</th>
              <td colSpan="3">{stockInfo.market_cap?.replace(/\n\t+/g, '')} ({stockInfo.market_cap_rank})</td>
            </tr>
            <tr>
              <th>외국인비율</th>
              <td>{stockInfo.foreign_ownership_ratio}</td>
              <th>발행주식수</th>
              <td>{Number(stockInfo.shares_outstanding).toLocaleString()}</td>
            </tr>
            <tr>
              <th>52주 최고</th>
              <td>{Number(stockInfo.fifty_two_week_high).toLocaleString()}</td>
              <th>52주 최저</th>
              <td>{Number(stockInfo.fifty_two_week_low).toLocaleString()}</td>
            </tr>
            <tr>
              <th>PER</th>
              <td>{stockInfo.per_info}</td>
              <th>PBR</th>
              <td>{stockInfo.pbr_info}</td>
            </tr>
            <tr>
              <th>EPS</th>
              <td>{stockInfo.eps_info}</td>
              <th>BPS</th>
              <td>{stockInfo.bps_info}</td>
            </tr>
            <tr>
              <th>예상 PER</th>
              <td>{stockInfo.estimated_per_info}</td>
              <th>배당수익률</th>
              <td>{stockInfo.dividend_yield_info}</td>
            </tr>
            <tr>
              <th>예상 EPS</th>
              <td>{stockInfo.estimated_eps_info}</td>
              <th>업종 PER</th>
              <td>{stockInfo.industry_per_info}</td>
            </tr>
          </tbody>
        </table>
        
        <div className="text-center mt-3">
          <a 
            href={stockInfo.item_main_url} 
            className="btn btn-sm btn-outline-primary" 
            target="_blank" 
            rel="noopener noreferrer"
          >
            네이버 금융에서 보기
          </a>
        </div>
      </div>
    );
  };

  // 사이드바 탭 네비게이션 컴포넌트 - 버튼에 텍스트 추가
  const SidebarNav = ({ activeTab, onChange }) => {
    return (
      <div className="sidebar-nav">
        <div className="nav nav-pills nav-fill">
          <button 
            className={`nav-link ${activeTab === 'dictionary' ? 'active' : ''}`}
            onClick={() => onChange('dictionary')}
            title="용어사전"
          >
            <div className="d-flex flex-column align-items-center">
              <i className="bi bi-book"></i>
              <small>용어사전</small>
            </div>
          </button>
          <button 
            className={`nav-link ${activeTab === 'news' ? 'active' : ''}`}
            onClick={() => onChange('news')}
            title="뉴스"
          >
            <div className="d-flex flex-column align-items-center">
              <i className="bi bi-newspaper"></i>
              <small>뉴스</small>
            </div>
          </button>
          <button 
            className={`nav-link ${activeTab === 'stock' ? 'active' : ''}`}
            onClick={() => onChange('stock')}
            title="주가정보"
          >
            <div className="d-flex flex-column align-items-center">
              <i className="bi bi-graph-up"></i>
              <small>주가정보</small>
            </div>
          </button>
          <button 
            className={`nav-link ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => onChange('chat')}
            title="AI 질의응답"
          >
            <div className="d-flex flex-column align-items-center">
              <i className="bi bi-chat-dots"></i>
              <small>질의응답</small>
            </div>
          </button>
        </div>
      </div>
    );
  };

  // 사이드바 콘텐츠 렌더링 함수 - 'toc' 옵션 제거
  const renderSidebarContent = () => {
    switch (sidebarContentType) {
      case 'news':
        return <CompanyNews news={news} isLoading={isNewsLoading} />;
      case 'stock':
        return <StockInfo stockInfo={stockInfo} isLoading={isStockLoading} chartUrl={stockChartUrl} />;
      case 'dictionary':
        return (
          <DictionaryComponent 
            dictionary={dictionary} 
            isLoading={isDictionaryLoading} 
            expandedTerms={expandedTerms}
            onToggleTerm={toggleTermExpansion}
          />
        );
      case 'chat':
      default:
        return <ChatComponent />;
    }
  };

  return (
    <aside ref={sidebarRef} className={`sidebar ${isHeaderHidden ? 'sidebar-top' : ''} ${showSidebar ? 'show' : ''}`}>
      <SidebarNav activeTab={sidebarContentType} onChange={changeSidebarContent} />
      <div className="sidebar-content">
        {renderSidebarContent()}
      </div>
    </aside>
  );
};

export default ReportSidebar;
