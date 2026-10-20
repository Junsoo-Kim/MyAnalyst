package khu_swcon.myanalyst.shared.persistence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;

/**
 * 모듈 분리 이전에 Hibernate가 만든 "다른 모듈 테이블을 가리키는 FK"를 제거하는 일회성 마이그레이션.
 *
 * <p>엔티티 간 JPA 연관관계를 ID 참조로 바꿔도 ddl-auto=update는 기존 FK를 지우지 않는다. FK가 남아 있으면
 * 보고서 삭제가 (이제 이벤트로 나중에 지워지는) 채팅 행 때문에 실패한다. 각 모듈이 자기 테이블만 소유하고
 * 이후 서비스별 DB로 나누기 위한 단계이며, 모든 환경에 적용된 뒤에는 이 클래스를 지워도 된다.
 * 같은 모듈 안의 FK(report_job_attempt → report_jobs)는 유지한다.
 */
@Component
public class ModuleBoundaryMigration implements ApplicationRunner {
    private static final Logger log = LoggerFactory.getLogger(ModuleBoundaryMigration.class);

    private static final String DROP_CROSS_MODULE_FOREIGN_KEYS = """
            DO $$
            DECLARE r record;
            BEGIN
              FOR r IN
                SELECT con.conrelid::regclass::text AS tbl, con.conname
                FROM pg_constraint con
                WHERE con.contype = 'f'
                  AND (con.conrelid::regclass::text, con.confrelid::regclass::text) IN (
                    ('chats', 'reports'), ('dictionary', 'reports'), ('reports', 'users'),
                    ('report_jobs', 'users'), ('report_jobs', 'reports'))
              LOOP
                RAISE NOTICE 'dropping cross-module foreign key %.%', r.tbl, r.conname;
                EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
              END LOOP;
            END $$
            """;

    private final DataSource dataSource;

    public ModuleBoundaryMigration(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            if (!"PostgreSQL".equalsIgnoreCase(connection.getMetaData().getDatabaseProductName())) {
                return;
            }
        }
        new JdbcTemplate(dataSource).execute(DROP_CROSS_MODULE_FOREIGN_KEYS);
        log.info("Cross-module foreign keys checked and removed where present");
    }
}
