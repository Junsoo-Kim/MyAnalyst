package khu_swcon.myanalyst.auth.token;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.HexFormat;
import java.util.Optional;
import java.util.UUID;

/**
 * access token(짧은 수명 JWT)과 refresh token(긴 수명, 서버 저장)을 발급한다.
 *
 * <ul>
 *   <li>access token은 서버에 저장하지 않는다. Gateway가 서명과 만료만 보고 통과시키므로, 이 서비스나 Redis가
 *       내려가도 이미 발급된 토큰은 만료 전까지 쓸 수 있다. 대신 로그아웃해도 만료 전까지는 유효하다 —
 *       그래서 수명을 짧게(기본 15분) 둔다.</li>
 *   <li>refresh token은 무작위 값이고, Redis에는 그 해시만 저장한다(Redis가 유출돼도 토큰을 쓸 수 없다).
 *       한 번 쓰면 지우고 새로 발급한다(rotation). 이미 쓴 토큰이 다시 오면 거절된다.</li>
 * </ul>
 */
@Service
public class TokenService {
    private static final String REFRESH_KEY_PREFIX = "auth:refresh:";
    private static final SecureRandom RANDOM = new SecureRandom();

    private final SigningKeyProvider keys;
    private final StringRedisTemplate redis;
    private final String issuer;
    private final Duration accessTtl;
    private final Duration refreshTtl;

    public TokenService(SigningKeyProvider keys, StringRedisTemplate redis,
                        @Value("${app.jwt.issuer}") String issuer,
                        @Value("${app.jwt.access-ttl}") Duration accessTtl,
                        @Value("${app.jwt.refresh-ttl}") Duration refreshTtl) {
        this.keys = keys;
        this.redis = redis;
        this.issuer = issuer;
        this.accessTtl = accessTtl;
        this.refreshTtl = refreshTtl;
    }

    public record IssuedTokens(String accessToken, Duration accessTtl, String refreshToken, Duration refreshTtl) {
    }

    public IssuedTokens issue(String userId) {
        String refreshToken = randomToken();
        redis.opsForValue().set(REFRESH_KEY_PREFIX + hash(refreshToken), userId, refreshTtl);
        return new IssuedTokens(signAccessToken(userId), accessTtl, refreshToken, refreshTtl);
    }

    /** refresh token을 한 번 쓰고 버린다. 유효하면 새 토큰 쌍을, 없거나 이미 쓴 토큰이면 empty를 돌려준다. */
    public Optional<IssuedTokens> rotate(String refreshToken) {
        if (refreshToken == null || refreshToken.isBlank()) {
            return Optional.empty();
        }
        String userId = redis.opsForValue().getAndDelete(REFRESH_KEY_PREFIX + hash(refreshToken));
        return Optional.ofNullable(userId).map(this::issue);
    }

    public void revoke(String refreshToken) {
        if (refreshToken != null && !refreshToken.isBlank()) {
            redis.delete(REFRESH_KEY_PREFIX + hash(refreshToken));
        }
    }

    private String signAccessToken(String userId) {
        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject(userId)
                .jwtID(UUID.randomUUID().toString())
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plus(accessTtl)))
                .build();
        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
                .keyID(keys.signingKey().getKeyID())
                .type(JOSEObjectType.JWT)
                .build();
        SignedJWT jwt = new SignedJWT(header, claims);
        try {
            jwt.sign(new RSASSASigner(keys.signingKey()));
        } catch (JOSEException e) {
            throw new IllegalStateException("JWT signing failed", e);
        }
        return jwt.serialize();
    }

    private static String randomToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String hash(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
