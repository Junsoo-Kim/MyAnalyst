import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';

const Login = () => {
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

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
  }, []);
  
  const handleChange = (e) => {
    const { id, value } = e.target;
    setFormData({
      ...formData,
      [id]: value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    // 폼 유효성 검사
    if (!formData.username || !formData.password) {
      setError('아이디와 비밀번호를 입력해주세요.');
      return;
    }

    try {
      setIsLoading(true);
      
      const response = await apiFetch('/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userid: formData.username,
          password: formData.password
        }),
        credentials: 'include' // 쿠키를 주고받기 위해 필요
      });

      if (response.ok) {        
        // 쿠키에 사용자 ID 저장 (1일 유효)
        document.cookie = `userId=${formData.username}; path=/; max-age=86400; SameSite=Lax`;
        
        // 홈페이지로 리다이렉트
        navigate('/');
      } else {
        // 서버에서 오류 응답이 온 경우
        const errorData = await response.json();
        setError(errorData.message || '로그인에 실패했습니다. 아이디와 비밀번호를 확인해주세요.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다. 다시 시도해주세요.');
      console.error('Login error:', err);
    } finally {
      setIsLoading(false);
    }
  };
  
  return (
    <main className="main">
      {/* Login Section */}
      <section id="login" className="login section">
        <div className="container">
          <div className="row justify-content-center">
            <div className="col-lg-6 col-md-8">
              <div className="card shadow-lg border-0 rounded-lg mt-5" data-aos="fade-up">
                <div className="card-header bg-white">
                  <h3 className="text-center my-4">로그인</h3>
                </div>
                <div className="card-body p-4">
                  {error && (
                    <div className="alert alert-danger" role="alert">
                      {error}
                    </div>
                  )}
                  
                  <form onSubmit={handleSubmit}>
                    <div className="mb-4">
                      <label htmlFor="username" className="form-label">아이디</label>
                      <div className="input-group">
                        <span className="input-group-text"><i className="bi bi-person"></i></span>
                        <input 
                          type="text" 
                          className="form-control" 
                          id="username" 
                          placeholder="아이디를 입력하세요" 
                          value={formData.username}
                          onChange={handleChange}
                          required 
                        />
                      </div>
                    </div>
                    
                    <div className="mb-4">
                      <label htmlFor="password" className="form-label">비밀번호</label>
                      <div className="input-group">
                        <span className="input-group-text"><i className="bi bi-lock"></i></span>
                        <input 
                          type="password" 
                          className="form-control" 
                          id="password" 
                          placeholder="비밀번호를 입력하세요" 
                          value={formData.password}
                          onChange={handleChange}
                          required 
                        />
                      </div>
                    </div>
                  
                    <div className="d-flex align-items-center justify-content-center mt-4 mb-0">
                      <button 
                        type="submit" 
                        className="btn btn-primary btn-lg w-100"
                        disabled={isLoading}
                      >
                        {isLoading ? (
                          <>
                            <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                            <span className="ms-2">처리중...</span>
                          </>
                        ) : '로그인'}
                      </button>
                    </div>
                  </form>
                </div>
                <div className="card-footer text-center py-3 bg-white">
                  <div className="small">계정이 없으신가요? <Link to="/signup">회원가입</Link></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>{/* /Login Section */}
    </main>
  );
};

export default Login;
