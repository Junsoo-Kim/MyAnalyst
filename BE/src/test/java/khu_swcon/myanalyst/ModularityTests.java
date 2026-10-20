package khu_swcon.myanalyst;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

/**
 * Fails the build when a module reaches into another module's internals or modules depend on each other in a cycle.
 * The generated diagrams (target/spring-modulith-docs) document the boundaries the MSA split will follow.
 */
class ModularityTests {

    private final ApplicationModules modules = ApplicationModules.of(MyanalystApplication.class);

    @Test
    void verifiesModuleBoundaries() {
        modules.forEach(System.out::println);
        new Documenter(modules).writeDocumentation();
        modules.verify();
    }
}
