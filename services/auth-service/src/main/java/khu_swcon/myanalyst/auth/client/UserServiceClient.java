package khu_swcon.myanalyst.auth.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.Map;

/**
 * user-service 내부 API(/internal/credentials/verify) 클라이언트. 비밀번호 해시는 user-service 밖으로 나오지 않는다.
 */
@Component
public class UserServiceClient {

    public enum Verification { OK, UNKNOWN_USER, WRONG_PASSWORD }

    public static class UserServiceUnavailableException extends RuntimeException {
        public UserServiceUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final RestClient restClient;

    public UserServiceClient(@Value("${app.services.user.base-url}") String baseUrl,
                             @Value("${app.services.user.timeout}") Duration timeout,
                             @Value("${app.internal-token}") String internalToken) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(timeout);
        requestFactory.setReadTimeout(timeout);
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .defaultHeader("X-Internal-Token", internalToken)
                .build();
    }

    public Verification verify(String userId, String password) {
        try {
            HttpStatusCode status = restClient.post()
                    .uri("/internal/credentials/verify")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("userid", userId, "password", password))
                    .exchange((request, response) -> response.getStatusCode());
            if (status.is2xxSuccessful()) {
                return Verification.OK;
            }
            if (status.value() == 404) {
                return Verification.UNKNOWN_USER;
            }
            if (status.value() == 401 || status.value() == 400) {
                return Verification.WRONG_PASSWORD;
            }
            throw new UserServiceUnavailableException("user-service returned " + status, null);
        } catch (ResourceAccessException e) {
            throw new UserServiceUnavailableException("user-service unreachable: " + e.getMessage(), e);
        }
    }
}
