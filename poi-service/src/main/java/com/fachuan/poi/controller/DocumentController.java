package com.fachuan.poi.controller;

import com.fachuan.poi.model.ComplaintRequest;
import com.fachuan.poi.model.DocumentRequest;
import com.fachuan.poi.model.ReportRequest;
import com.fachuan.poi.service.ComplaintService;
import com.fachuan.poi.service.ReportService;
import com.fachuan.poi.service.TemplateService;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * REST controller for document generation endpoints.
 * All endpoints accept JSON and return DOCX bytes.
 */
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final ComplaintService complaintService;
    private final ReportService reportService;
    private final TemplateService templateService;

    public DocumentController(
            ComplaintService complaintService,
            ReportService reportService,
            TemplateService templateService) {
        this.complaintService = complaintService;
        this.reportService = reportService;
        this.templateService = templateService;
    }

    /**
     * Health check.
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of(
            "status", "ok",
            "service", "poi-service",
            "version", "1.0.0",
            "poi_version", "5.3.0"
        );
    }

    /**
     * Generate 起诉状 (complaint).
     */
    @PostMapping("/complaint")
    public ResponseEntity<byte[]> generateComplaint(@RequestBody ComplaintRequest request) {
        try {
            byte[] docx = complaintService.generate(request);
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"complaint.docx\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(docx);
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }

    /**
     * Generate 尽调报告 (due diligence report).
     */
    @PostMapping("/report")
    public ResponseEntity<byte[]> generateReport(@RequestBody ReportRequest request) {
        try {
            byte[] docx = reportService.generate(request);
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"report.docx\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(docx);
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }

    /**
     * Render a .docx template with context data.
     */
    @PostMapping("/template/render")
    public ResponseEntity<byte[]> renderTemplate(@RequestBody DocumentRequest request) {
        try {
            byte[] docx = templateService.render(request);
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"" + request.getTemplateName() + "\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(docx);
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }

    /**
     * List available templates.
     */
    @GetMapping("/templates")
    public ResponseEntity<?> listTemplates() {
        try {
            return ResponseEntity.ok(Map.of("templates", templateService.listTemplates()));
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(Map.of("error", e.getMessage()));
        }
    }
}
