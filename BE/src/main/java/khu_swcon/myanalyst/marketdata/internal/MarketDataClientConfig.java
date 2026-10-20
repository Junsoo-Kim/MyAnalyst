package khu_swcon.myanalyst.marketdata.internal;

import khu_swcon.myanalyst.shared.web.ServiceClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;

@Configuration
public class MarketDataClientConfig {

    @Bean
    public WebClient marketDataWebClient(
            @Value("${app.services.market-data.base-url}") String baseUrl,
            @Value("${app.services.connect-timeout}") Duration connectTimeout,
            @Value("${app.services.response-timeout}") Duration responseTimeout) {
        return ServiceClients.create(baseUrl, connectTimeout, responseTimeout);
    }
}
