# Multi-stage build for POI Service
# Java 25 + Ubuntu Noble (glibc) for proper Chinese font rendering
FROM eclipse-temurin:25-jdk-noble AS builder

WORKDIR /app
COPY pom.xml .
COPY src ./src

RUN apt-get update && \
    apt-get install -y --no-install-recommends maven && \
    rm -rf /var/lib/apt/lists/* && \
    mvn clean package -DskipTests

# ── Runtime ──
FROM eclipse-temurin:25-jre-noble

# Install Chinese fonts (Noto CJK) + wget for health check
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-noto-cjk \
        wget && \
    rm -rf /var/lib/apt/lists/* && \
    fc-cache -fv

# Non-root user
RUN groupadd -r spring && useradd -r -g spring spring

WORKDIR /app
COPY --from=builder /app/target/poi-service-1.0.0.jar app.jar
RUN chown spring:spring app.jar

USER spring

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q --spider http://localhost:8090/api/documents/health || exit 1

ENTRYPOINT ["java", \
    "-XX:+UseContainerSupport", \
    "-XX:MaxRAMPercentage=75.0", \
    "-XX:+UseG1GC", \
    "-jar", "app.jar"]
