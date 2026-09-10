import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';

const Header = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const isHome = location.pathname === '/';
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  
  useEffect(() => {
    // Check if user is logged in by looking for userid cookie
    const checkLoginStatus = () => {
      const cookies = document.cookie.split(';');
      const userIdCookie = cookies.find(cookie => cookie.trim().startsWith('userId='));
      setIsLoggedIn(!!userIdCookie);
    };
    
    checkLoginStatus();
    
    // Also check on mount and route changes
    window.addEventListener('storage', checkLoginStatus);
    return () => window.removeEventListener('storage', checkLoginStatus);
  }, [location]);
  
  useEffect(() => {
    const toggleScrolled = () => {
      const selectBody = document.querySelector('body');
      const selectHeader = document.querySelector('#header');
      if (!selectHeader || !selectHeader.classList.contains('fixed-top')) return;
      window.scrollY > 100 ? selectBody.classList.add('scrolled') : selectBody.classList.remove('scrolled');
    };

    document.addEventListener('scroll', toggleScrolled);
    window.addEventListener('load', toggleScrolled);
    
    return () => {
      document.removeEventListener('scroll', toggleScrolled);
      window.removeEventListener('load', toggleScrolled);
    };
  }, []);
  
  const handleMobileNavToggle = () => {
    document.querySelector('body').classList.toggle('mobile-nav-active');
    document.querySelector('.mobile-nav-toggle').classList.toggle('bi-list');
    document.querySelector('.mobile-nav-toggle').classList.toggle('bi-x');
  };

  const handleLogout = async () => {
    try {
      await apiFetch('/sessions', { method: 'DELETE' });
    } catch (error) {
      console.error('Logout request failed:', error);
    }
    // Delete the userid cookie
    document.cookie = "userId=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    // Update login status
    setIsLoggedIn(false);
    // Redirect to home page after logout
    navigate('/');
  };

  return (
    <header id="header" className={`header d-flex align-items-center fixed-top ${isHome ? 'index-page' : ''}`}>
      <div className="container-fluid container-xl position-relative d-flex align-items-center">
        <Link to="/" className="logo d-flex align-items-center me-auto">
          <img src="/assets/img/logo.png" alt="Logo" />
          <h1 className="sitename">MyAnalyst</h1>
        </Link>

        <nav id="navmenu" className="navmenu d-none">
          <ul>
            <li><Link to="/#hero" className={location.hash === '#hero' ? 'active' : ''}>Home</Link></li>
            <li><Link to="/#about" className={location.hash === '#about' ? 'active' : ''}>About</Link></li>
          </ul>
          <i className="mobile-nav-toggle d-xl-none bi bi-list" onClick={handleMobileNavToggle}></i>
        </nav>

        {isLoggedIn ? (
          <>
            <Link className="btn-getstarted" onClick={handleLogout} to="/">로그아웃</Link>
            <Link className="btn-getstarted" to="/reports-list">보고서 목록</Link>
          </>
        ) : (
          <>
            <Link className="btn-getstarted" to="/login">로그인</Link>
            <Link className="btn-getstarted" to="/signup">회원가입</Link>
          </>
        )}
      </div>
    </header>
  );
};

export default Header;
