package com.fachuan.poi.service;

import com.deepoove.poi.XWPFTemplate;
import com.fachuan.poi.model.DocumentRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Template-based document rendering using poi-tl.
 * Supports conditional rendering, loops, tables, images, etc.
 */
@Service
public class TemplateService {

    @Value("${poi.service.template-dir:classpath:templates}")
    private String templateDir;

    private Path templatesPath;

    /**
     * Render a .docx template with context data.
     *
     * @param request containing templateName and context map
     * @return rendered DOCX as byte array
     * @throws IOException if template not found or rendering fails
     */
    public byte[] render(DocumentRequest request) throws IOException {
        Path templatePath = resolveTemplate(request.getTemplateName());
        if (templatePath == null || !Files.exists(templatePath)) {
            throw new IOException("Template not found: " + request.getTemplateName());
        }

        Map<String, Object> context = request.getContext();
        if (context == null) {
            context = Collections.emptyMap();
        }

        try {
            // Compile and render template using poi-tl
            XWPFTemplate template = XWPFTemplate.compile(
                templatePath.toString()
            ).render(context);

            // Convert to byte array
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            template.writeAndClose(out);
            template.close();

            return out.toByteArray();

        } catch (Exception e) {
            throw new IOException("Failed to render template: " + e.getMessage(), e);
        }
    }

    /**
     * List available templates.
     */
    public List<String> listTemplates() throws IOException {
        Path dir = getTemplatesPath();
        if (!Files.exists(dir) || !Files.isDirectory(dir)) {
            return Collections.emptyList();
        }

        try (var stream = Files.walk(dir)) {
            return stream
                .filter(p -> p.toString().endsWith(".docx"))
                .map(p -> dir.relativize(p).toString().replace("\\", "/"))
                .sorted()
                .collect(Collectors.toList());
        }
    }

    /**
     * Check if template exists.
     */
    public boolean templateExists(String templateName) {
        Path templatePath = resolveTemplate(templateName);
        return templatePath != null && Files.exists(templatePath);
    }

    /**
     * Get template absolute path.
     */
    public Path getTemplatePath(String templateName) {
        return resolveTemplate(templateName);
    }

    // ── Private Helpers ──

    private Path getTemplatesPath() {
        if (templatesPath != null) {
            return templatesPath;
        }

        if (templateDir.startsWith("classpath:")) {
            String classpath = templateDir.replace("classpath:", "");
            try {
                URI uri = getClass().getClassLoader().getResource(classpath).toURI();
                templatesPath = Paths.get(uri);
            } catch (Exception e) {
                // Fallback to file system path
                templatesPath = Paths.get("src/main/resources/" + classpath);
            }
        } else {
            templatesPath = Paths.get(templateDir);
        }

        return templatesPath;
    }

    private Path resolveTemplate(String name) {
        if (name == null || name.isBlank()) {
            return null;
        }

        // 1. Try classpath templates directory
        Path classpath = Paths.get("src/main/resources/templates");
        Path resolved = classpath.resolve(name);
        if (Files.exists(resolved)) {
            return resolved;
        }

        // 2. Try configured directory
        String configuredDir = templateDir.replace("classpath:", "src/main/resources/");
        Path configured = Paths.get(configuredDir).resolve(name);
        if (Files.exists(configured)) {
            return configured;
        }

        // 3. Try absolute path
        Path absolute = Paths.get(name);
        if (Files.exists(absolute)) {
            return absolute;
        }

        return null;
    }
}
