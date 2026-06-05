package com.fachuan.poi.controller;

import com.fachuan.poi.model.DocumentRequest;
import com.fachuan.poi.service.TemplateService;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Template rendering and listing endpoints.
 */
@RestController
@RequestMapping("/api/documents")
public class TemplateController {

    private final TemplateService templateService;

    public TemplateController(TemplateService templateService) {
        this.templateService = templateService;
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
