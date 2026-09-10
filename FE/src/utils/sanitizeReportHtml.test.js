import { sanitizeReportHtml } from './sanitizeReportHtml';

test('removes executable HTML from generated report content', () => {
  const sanitized = sanitizeReportHtml('<img src="x" onerror="window.__xss = true"><script>alert(1)</script><p>safe</p>');

  expect(sanitized).not.toContain('onerror');
  expect(sanitized).not.toContain('<script');
  expect(sanitized).toContain('<p>safe</p>');
});
