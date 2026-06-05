package com.fachuan.poi.service;

import com.fachuan.poi.model.DocumentRequest;
import org.apache.poi.xwpf.usermodel.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

/**
 * Generic template-based document rendering.
 * Loads a .docx template and replaces text placeholders with context values.
 * This is the POI equivalent of docxtpl's Jinja2-based rendering.
 */
@Service
public class TemplateService {

    @Value("${poi.service.template-dir:classpath:templates}")
    private String templateDir;

    /**
     * Render a .docx template by replacing text placeholders.
     * Placeholders use the format: {{key}}
     */
    public byte[] render(DocumentRequest request) throws IOException {
        Path templatePath = resolveTemplate(request.getTemplateName());
        if (templatePath == null || !Files.exists(templatePath)) {
            throw new IOException("Template not found: " + request.getTemplateName());
        }

        try (InputStream is = Files.newInputStream(templatePath);
             XWPFDocument doc = new XWPFDocument(is)) {

            Map<String, Object> context = request.getContext();
            if (context != null) {
                // Replace in paragraphs
                for (XWPFParagraph para : doc.getParagraphs()) {
                    replacePlaceholders(para, context);
                }
                // Replace in tables
                for (XWPFTable table : doc.getTables()) {
                    for (XWPFTableRow row : table.getRows()) {
                        for (XWPFTableCell cell : row.getTableCells()) {
                            for (XWPFParagraph para : cell.getParagraphs()) {
                                replacePlaceholders(para, context);
                            }
                        }
                    }
                }
                // Replace in headers
                for (XWPFHeader header : doc.getHeaderList()) {
                    for (XWPFParagraph para : header.getParagraphs()) {
                        replacePlaceholders(para, context);
                    }
                }
                // Replace in footers
                for (XWPFFooter footer : doc.getFooterList()) {
                    for (XWPFParagraph para : footer.getParagraphs()) {
                        replacePlaceholders(para, context);
                    }
                }
            }

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            doc.write(baos);
            return baos.toByteArray();
        }
    }

    /**
     * List available templates.
     */
    public java.util.List<String> listTemplates() throws IOException {
        java.util.List<String> templates = new java.util.ArrayList<>();
        Path dir = Paths.get(templateDir.replace("classpath:", ""));
        if (Files.exists(dir) && Files.isDirectory(dir)) {
            try (var stream = Files.walk(dir)) {
                stream.filter(p -> p.toString().endsWith(".docx"))
                      .forEach(p -> templates.add(dir.relativize(p).toString()));
            }
        }
        return templates;
    }

    // ── Internal ──

    private void replacePlaceholders(XWPFParagraph para, Map<String, Object> context) {
        String text = para.getText();
        if (text == null || !text.contains("{{")) return;

        for (Map.Entry<String, Object> entry : context.entrySet()) {
            String placeholder = "{{" + entry.getKey() + "}}";
            String value = entry.getValue() != null ? entry.getValue().toString() : "";
            text = text.replace(placeholder, value);
        }

        // Clear and rewrite runs
        if (!text.equals(para.getText())) {
            // Preserve formatting from first run
            XWPFRun templateRun = para.getRuns() != null && !para.getRuns().isEmpty()
                    ? para.getRuns().get(0) : null;

            // Remove all existing runs
            while (para.getRuns() != null && !para.getRuns().isEmpty()) {
                para.removeRun(0);
            }

            XWPFRun newRun = para.createRun();
            newRun.setText(text);

            // Inherit formatting from template run
            if (templateRun != null) {
                newRun.setBold(templateRun.isBold());
                newRun.setItalic(templateRun.isItalic());
                newRun.setFontSize(templateRun.getFontSizeAsDouble() != null
                        ? templateRun.getFontSizeAsDouble().intValue() : 12);
                if (templateRun.getFontFamily() != null) {
                    newRun.setFontFamily(templateRun.getFontFamily());
                }
                if (templateRun.getColor() != null) {
                    newRun.setColor(templateRun.getColor());
                }
            }
        }
    }

    private Path resolveTemplate(String name) {
        // Try classpath first
        Path classpath = Paths.get("src/main/resources/templates");
        Path resolved = classpath.resolve(name);
        if (Files.exists(resolved)) return resolved;

        // Try configured dir
        Path configured = Paths.get(templateDir.replace("classpath:", "src/main/resources/"));
        resolved = configured.resolve(name);
        if (Files.exists(resolved)) return resolved;

        // Try absolute
        Path absolute = Paths.get(name);
        if (Files.exists(absolute)) return absolute;

        return null;
    }
}
