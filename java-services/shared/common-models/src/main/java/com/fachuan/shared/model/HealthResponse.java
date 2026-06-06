package com.fachuan.shared.model;

import lombok.Data;

/**
 * Standard health check response DTO.
 * Shared across all Java services.
 */
@Data
public class HealthResponse {
    private String status;
    private String service;
    private String version;

    public static HealthResponse ok(String service, String version) {
        HealthResponse r = new HealthResponse();
        r.setStatus("ok");
        r.setService(service);
        r.setVersion(version);
        return r;
    }
}
