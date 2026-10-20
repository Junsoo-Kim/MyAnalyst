package khu_swcon.myanalyst.chat.internal;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/** 받은 X-Trace-Id(없으면 새로 만든 값)를 로그 MDC와 qa/stt 호출에 이어 붙인다. */
@Component
class TraceIdFilter extends OncePerRequestFilter {
    static final String HEADER = "X-Trace-Id";
    static final String TRACE_ID = "traceId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String incoming = request.getHeader(HEADER);
        String traceId = incoming == null || incoming.isBlank() ? UUID.randomUUID().toString() : incoming;
        MDC.put(TRACE_ID, traceId);
        try {
            response.setHeader(HEADER, traceId);
            chain.doFilter(request, response);
        } finally {
            MDC.remove(TRACE_ID);
        }
    }
}
