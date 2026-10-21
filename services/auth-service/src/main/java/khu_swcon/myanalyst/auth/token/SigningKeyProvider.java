package khu_swcon.myanalyst.auth.token;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.ParseException;
import java.util.UUID;

/**
 * JWT 서명 키(RSA 2048). 재시작할 때마다 새 키를 만들면 이미 발급한 토큰이 모두 무효가 되므로 고정된 곳에서 읽는다.
 * <ol>
 *   <li>{@code JWT_SIGNING_KEY}(JWK JSON, 비공개키 포함)가 있으면 그것을 쓴다. ECS에서는 Secrets Manager 값을 이 환경
 *       변수로 주입한다(태스크가 여러 개여도 같은 키, 디스크 불필요).</li>
 *   <li>없으면 키 파일을 읽고, 파일도 없으면 만들어 저장한다(로컬 compose는 볼륨에 보관).</li>
 * </ol>
 * 공개키만 {@link #publicJwkSet()}으로 내보내고, Gateway는 이것으로 서명을 검증한다.
 */
@Component
public class SigningKeyProvider {
    private static final Logger log = LoggerFactory.getLogger(SigningKeyProvider.class);

    private final RSAKey signingKey;

    public SigningKeyProvider(@Value("${app.jwt.key-json:}") String keyJson,
                              @Value("${app.jwt.key-file}") Path keyFile) throws IOException, ParseException, JOSEException {
        this.signingKey = keyJson.isBlank() ? loadOrCreate(keyFile) : fromEnvironment(keyJson);
    }

    private static RSAKey fromEnvironment(String keyJson) throws ParseException {
        RSAKey key = RSAKey.parse(keyJson);
        if (!key.isPrivate()) {
            throw new IllegalStateException("JWT_SIGNING_KEY must contain the private key");
        }
        log.info("Loaded JWT signing key kid={} from JWT_SIGNING_KEY", key.getKeyID());
        return key;
    }

    private static RSAKey loadOrCreate(Path keyFile) throws IOException, ParseException, JOSEException {
        if (Files.exists(keyFile)) {
            RSAKey key = RSAKey.parse(Files.readString(keyFile));
            log.info("Loaded JWT signing key kid={} from {}", key.getKeyID(), keyFile);
            return key;
        }
        RSAKey key = new RSAKeyGenerator(2048)
                .keyUse(KeyUse.SIGNATURE)
                .keyID(UUID.randomUUID().toString())
                .generate();
        Files.createDirectories(keyFile.toAbsolutePath().getParent());
        Files.writeString(keyFile, key.toJSONString());
        log.info("Generated new JWT signing key kid={} at {}", key.getKeyID(), keyFile);
        return key;
    }

    public RSAKey signingKey() {
        return signingKey;
    }

    public JWKSet publicJwkSet() {
        return new JWKSet(signingKey.toPublicJWK());
    }
}
