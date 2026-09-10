import DOMPurify from 'dompurify';

export const sanitizeReportHtml = (html) => DOMPurify.sanitize(html, {
  USE_PROFILES: { html: true }
});
