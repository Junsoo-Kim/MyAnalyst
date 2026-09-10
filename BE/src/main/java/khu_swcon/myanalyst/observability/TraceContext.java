package khu_swcon.myanalyst.observability;

import io.opentelemetry.api.trace.Span;
import org.slf4j.MDC;

import java.util.UUID;

public final class TraceContext {
    public static final String TRACE_ID = "traceId";

    private TraceContext() {
    }

    public static String currentTraceId() {
        String otelTraceId = Span.current().getSpanContext().getTraceId();
        if (otelTraceId != null && !otelTraceId.isBlank() && !otelTraceId.matches("0+")) {
            return otelTraceId;
        }
        String mdcTraceId = MDC.get(TRACE_ID);
        return mdcTraceId == null || mdcTraceId.isBlank() ? UUID.randomUUID().toString() : mdcTraceId;
    }

    public static void bind(String traceId) {
        MDC.put(TRACE_ID, traceId);
    }

    public static void clear() {
        MDC.remove(TRACE_ID);
    }
}
