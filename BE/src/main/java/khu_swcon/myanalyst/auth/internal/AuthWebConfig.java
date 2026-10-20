package khu_swcon.myanalyst.auth.internal;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AuthWebConfig implements WebMvcConfigurer {
    private final GatewayIdentityInterceptor gatewayIdentityInterceptor;

    public AuthWebConfig(GatewayIdentityInterceptor gatewayIdentityInterceptor) {
        this.gatewayIdentityInterceptor = gatewayIdentityInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(gatewayIdentityInterceptor);
    }
}
