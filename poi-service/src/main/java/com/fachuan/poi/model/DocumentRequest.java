package com.fachuan.poi.model;

import java.util.Map;

/**
 * Generic document generation request.
 */
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

    public String getTemplateName() { return templateName; }
    public void setTemplateName(String templateName) { this.templateName = templateName; }
    public Map<String, Object> getContext() { return context; }
    public void setContext(Map<String, Object> context) { this.context = context; }
    public String getOutputFormat() { return outputFormat; }
    public void setOutputFormat(String outputFormat) { this.outputFormat = outputFormat; }
}
