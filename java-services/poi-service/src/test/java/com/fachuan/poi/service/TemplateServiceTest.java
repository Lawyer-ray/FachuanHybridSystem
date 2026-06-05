package com.fachuan.poi.service;

import com.fachuan.poi.model.DocumentRequest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class TemplateServiceTest {

    @Autowired
    private TemplateService templateService;

    @Test
    void testListTemplates() throws IOException {
        List<String> templates = templateService.listTemplates();
        assertNotNull(templates);
        // templates目录为空，所以列表应该为空
        assertTrue(templates.isEmpty());
    }

    @Test
    void testTemplateExists() {
        // 测试不存在的模板
        assertFalse(templateService.templateExists("nonexistent.docx"));
    }

    @Test
    void testRenderNonexistentTemplate() {
        Map<String, Object> context = Map.of("name", "test");
        DocumentRequest request = new DocumentRequest("nonexistent.docx", context);

        assertThrows(IOException.class, () -> {
            templateService.render(request);
        });
    }
}
