/**
 * Cross-cutting infrastructure (errors, tracing, HTTP clients, caching) that every module may use.
 * Kept open on purpose: it carries no business rules, so depending on it cannot couple domains.
 */
@ApplicationModule(type = ApplicationModule.Type.OPEN)
package khu_swcon.myanalyst.shared;

import org.springframework.modulith.ApplicationModule;
