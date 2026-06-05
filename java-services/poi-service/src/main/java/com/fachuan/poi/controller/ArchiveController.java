package com.fachuan.poi.controller;

import com.fachuan.poi.model.ArchiveRequest;
import com.fachuan.poi.service.ArchiveDocService;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/**
 * Archive document generation endpoints.
 */
@RestController
@RequestMapping("/api/documents/archive")
public class ArchiveController {

    private final ArchiveDocService archiveDocService;

    public ArchiveController(ArchiveDocService archiveDocService) {
        this.archiveDocService = archiveDocService;
    }

    @PostMapping("/case-cover")
    public ResponseEntity<byte[]> generateCaseCover(@RequestBody ArchiveRequest request) {
        try {
            byte[] docx = archiveDocService.generateCaseCover(request);
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"case_cover.docx\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(docx);
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }

    @PostMapping("/closing-register")
    public ResponseEntity<byte[]> generateClosingRegister(@RequestBody ArchiveRequest request) {
        try {
            byte[] docx = archiveDocService.generateClosingRegister(request);
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"closing_register.docx\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(docx);
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }

    @PostMapping("/catalog")
    public ResponseEntity<byte[]> generateCatalog(@RequestBody ArchiveRequest request) {
        try {
            byte[] docx = archiveDocService.generateCatalog(request);
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"catalog.docx\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(docx);
        } catch (Exception e) {
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }
}
