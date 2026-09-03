package khu_swcon.myanalyst.config;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/**
 * 뉴스/주가처럼 외부(RAG 서버 -> 네이버 크롤링)를 매번 다시 호출하면 느리고
 * 불필요한 부하를 주는 조회를 Redis(ElastiCache)에 캐싱한다.
 * 캐시 이름별로 TTL을 다르게 둬서, 실시간성이 중요한 주가는 짧게, 뉴스는 길게 유지한다.
 */
@Configuration
@EnableCaching
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaultConfig = RedisCacheConfiguration.defaultCacheConfig()
                .disableCachingNullValues()
                .entryTtl(Duration.ofMinutes(5))
                .serializeValuesWith(RedisSerializationContext.SerializationPair
                        .fromSerializer(new GenericJackson2JsonRedisSerializer()));

        Map<String, RedisCacheConfiguration> perCacheConfig = new HashMap<>();
        // 뉴스: 크롤링 결과가 자주 바뀌지 않으므로 5분
        perCacheConfig.put("news", defaultConfig.entryTtl(Duration.ofMinutes(5)));
        // 주가: 실시간성이 중요하므로 1분
        perCacheConfig.put("stocks", defaultConfig.entryTtl(Duration.ofMinutes(1)));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaultConfig)
                .withInitialCacheConfigurations(perCacheConfig)
                .build();
    }
}
