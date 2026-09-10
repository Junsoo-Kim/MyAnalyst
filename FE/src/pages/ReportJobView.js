import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiFetch, apiUrl } from '../api/client';

const TERMINAL_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED']);

export default function ReportJobView() {
  const navigate = useNavigate();
  const jobId = new URLSearchParams(useLocation().search).get('id');
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!jobId) {
      navigate('/company-analysis');
      return undefined;
    }
    let active = true;
    const refresh = async () => {
      try {
        const response = await apiFetch(`/report-jobs/${jobId}`);
        if (!response.ok) throw new Error('작업 상태를 불러오지 못했습니다.');
        if (active) setJob(await response.json());
      } catch (requestError) {
        if (active) setError(requestError.message);
      }
    };
    refresh();
    const stream = new EventSource(apiUrl(`/report-jobs/${jobId}/events`), { withCredentials: true });
    stream.addEventListener('report-job', (event) => {
      if (active) setJob(JSON.parse(event.data));
    });
    stream.onerror = () => stream.close();
    const poller = window.setInterval(refresh, 2000);
    return () => {
      active = false;
      stream.close();
      window.clearInterval(poller);
    };
  }, [jobId, navigate]);

  useEffect(() => {
    if (job?.status === 'SUCCEEDED' && job.reportId) {
      navigate(`/report-view?id=${job.reportId}`, { replace: true });
    }
  }, [job, navigate]);

  const cancel = async () => {
    const response = await apiFetch(`/report-jobs/${jobId}/cancel`, { method: 'POST' });
    if (response.ok) setJob(await response.json());
  };

  if (error) return <section className="section"><div className="container"><p>{error}</p></div></section>;
  if (!job) return <section className="section"><div className="container"><p>보고서 작업을 준비하고 있습니다…</p></div></section>;

  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 720 }}>
        <h2>보고서 생성 중</h2>
        <p>{job.message || job.status}</p>
        <div className="progress" role="progressbar" aria-valuenow={job.progress} aria-valuemin="0" aria-valuemax="100">
          <div className="progress-bar" style={{ width: `${job.progress}%` }}>{job.progress}%</div>
        </div>
        <p className="mt-3">상태: {job.status} · 시도: {job.attemptCount}</p>
        {job.status === 'FAILED' && <p className="text-danger">{job.error || '생성에 실패했습니다.'}</p>}
        {!TERMINAL_STATUSES.has(job.status) && <button className="btn btn-outline-danger" onClick={cancel}>작업 취소</button>}
        {TERMINAL_STATUSES.has(job.status) && job.status !== 'SUCCEEDED' && <button className="btn btn-primary" onClick={() => navigate('/company-analysis')}>새 보고서 만들기</button>}
      </div>
    </section>
  );
}
