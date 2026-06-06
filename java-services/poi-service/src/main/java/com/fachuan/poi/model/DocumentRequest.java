package com.fachuan.poi.model;

import java.util.Map;
import lombok.Data;

/**
 * Generic document generation request.
 */
@Data
public class DocumentRequest {

    private String templateName;
    private Map<String, Object> context;
    private String outputFormat; // "docx" or "pdf"

    public DocumentRequest() {}

    public DocumentRequest(String templateName, Map<String, Object> context) {
        this.templateName = templateName;
        this.context = context;
        this.outputFormat = "docx";
    }
}
