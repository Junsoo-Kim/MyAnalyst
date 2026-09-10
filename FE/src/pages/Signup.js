import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';

const Signup = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: '',
    password: '',
    password2: ''
  });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

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

    // 간단한 폼 유효성 검사
    if (formData.password !== formData.password2) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }

    try {
      setIsLoading(true);
      
      const response = await apiFetch('/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userid: formData.name,
          password: formData.password
        }),
      });

      if (response.ok) {
        // 회원가입 성공
        alert('회원가입이 완료되었습니다.');
        navigate('/login'); // 로그인 페이지로 이동
      } else {
        // 서버에서 오류 응답이 온 경우
        const errorData = await response.json();
        setError(errorData.message || '회원가입 중 오류가 발생했습니다.');
      }
    } catch (err) {
      setError('서버 연결에 실패했습니다. 다시 시도해주세요.');
      console.error('Signup error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main>
      <section className="section">
        <div className="container">
          <div className="row justify-content-center">
            <div className="col-lg-5">
              <div className="card p-4">
                <div className="card-body">
                  <h2 className="text-center mb-4">회원가입</h2>
                  
                  {error && (
                    <div className="alert alert-danger" role="alert">
                      {error}
                    </div>
                  )}
                  
                  <form onSubmit={handleSubmit}>
                    <div className="mb-3">
                      <label htmlFor="name" className="form-label">이름</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        id="name" 
                        value={formData.name}
                        onChange={handleChange}
                        required 
                      />
                    </div>
                    <div className="mb-3">
                      <label htmlFor="password" className="form-label">비밀번호</label>
                      <input 
                        type="password" 
                        className="form-control" 
                        id="password" 
                        value={formData.password}
                        onChange={handleChange}
                        required 
                      />
                    </div>
                    <div className="mb-3">
                      <label htmlFor="password2" className="form-label">비밀번호 확인</label>
                      <input 
                        type="password" 
                        className="form-control" 
                        id="password2" 
                        value={formData.password2}
                        onChange={handleChange}
                        required 
                      />
                    </div>
                    <button 
                      type="submit" 
                      className="btn btn-primary w-100"
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <>
                          <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                          <span className="ms-2">처리중...</span>
                        </>
                      ) : '회원가입'}
                    </button>
                  </form>
                  <div className="mt-4 text-center">
                    <p>이미 계정이 있으신가요? <Link to="/login">로그인</Link></p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};

export default Signup;
