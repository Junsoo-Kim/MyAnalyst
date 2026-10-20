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
 * JWT 서명 키(RSA 2048). 키 파일(JWK, 비공개키 포함)이 있으면 읽고, 없으면 만들어 저장한다.
 * 재시작할 때마다 새 키를 만들면 이미 발급한 토큰이 모두 무효가 되므로 볼륨에 보관한다.
 * 공개키만 {@link #publicJwkSet()}으로 내보내고, Gateway는 이것으로 서명을 검증한다.
 */
@Component
public class SigningKeyProvider {
    private static final Logger log = LoggerFactory.getLogger(SigningKeyProvider.class);

    private final RSAKey signingKey;

    public SigningKeyProvider(@Value("${app.jwt.key-file}") Path keyFile) throws IOException, ParseException, JOSEException {
        this.signingKey = loadOrCreate(keyFile);
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
