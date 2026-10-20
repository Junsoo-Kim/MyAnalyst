FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /app

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -B -q dependency:go-offline

COPY src ./src
RUN ./mvnw -B -q clean package -DskipTests

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 1001 spring \
    && mkdir -p /app/data && chown spring /app/data
COPY --from=build /app/target/*.jar app.jar
# JWT signing key (JWK) is kept here; mount a volume so restarts keep issued tokens valid.
ENV JWT_KEY_FILE=/app/data/jwt-signing-key.json
VOLUME /app/data
USER spring

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fs http://localhost:8080/actuator/health | grep -q '"status":"UP"' || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
