import React, { useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';

// Components
import Header from './components/Header';
import Footer from './components/Footer';
import ScrollTop from './components/ScrollTop';
import Preloader from './components/Preloader';

// Pages
import Home from './pages/Home';
import Login from './pages/Login';
import Signup from './pages/Signup';
import ReportsList from './pages/ReportsList';
import ReportView from './pages/ReportView';
import CompanyAnalysis from './pages/CompanyAnalysis';
import ReportJobView from './pages/ReportJobView';

// Main CSS
import './App.css';

function App() {
  useEffect(() => {
    // 외부 스크립트가 제대로 로드되었는지 확인
    const checkScripts = () => {
      if (!window.GLightbox) {
        console.warn('GLightbox is not loaded properly.');
      }
      if (!window.AOS) {
        console.warn('AOS is not loaded properly.');
      }
    };

    // DOM이 완전히 로드된 후 실행
    window.addEventListener('load', checkScripts);
    
    return () => {
      window.removeEventListener('load', checkScripts);
    };
  }, []);

  return (
    <>
      <Preloader />
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/reports-list" element={<ReportsList />} />
          <Route path="/report-view" element={<ReportView />} />
          <Route path="/company-analysis" element={<CompanyAnalysis />} />
          <Route path="/report-job" element={<ReportJobView />} />
        </Routes>
      </main>
      <Footer />
      <ScrollTop />
    </>
  );
}

export default App;
