package com.fachuan.poi.controller;

import com.fachuan.poi.model.ContractFormatConfig;
import com.fachuan.poi.model.ContractFormatRequest;
import com.fachuan.poi.service.ContractFormatService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 合同格式化控制器
 */
@RestController
@RequestMapping("/api/documents/contract")
@Slf4j
public class ContractController {

    private final ContractFormatService formatService;

    public ContractController(ContractFormatService formatService) {
        this.formatService = formatService;
    }

    /**
     * 格式化合同文档
     */
    @PostMapping("/format")
    public ResponseEntity<byte[]> formatContract(
            @RequestBody ContractFormatRequest request) {

        try {
            // 1. 验证输入
            if (request.getDocxBytes() == null || request.getDocxBytes().length == 0) {
                return ResponseEntity.badRequest()
                    .body("{\"error\": \"DOCX file is required\"}".getBytes());
            }

            // 2. 获取配置（使用默认配置或自定义配置）
            ContractFormatConfig config = request.getConfig() != null
                ? request.getConfig()
                : ContractFormatConfig.defaultConfig();

            // 3. 执行格式化
            byte[] formatted = formatService.format(request.getDocxBytes(), config);

            // 4. 生成输出文件名
            String outputName = request.getOutputFileName() != null
                ? request.getOutputFileName()
                : "formatted_contract.docx";

            // 5. 返回格式化后的文件
            return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"" + outputName + "\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(formatted);

        } catch (Exception e) {
            log.error("合同格式化失败", e);
            return ResponseEntity.internalServerError()
                .body(("{\"error\": \"" + e.getMessage() + "\"}").getBytes());
        }
    }

    /**
     * 健康检查
     */
    @GetMapping("/health")
    public ResponseEntity<?> healthCheck() {
        return ResponseEntity.ok(java.util.Map.of(
            "status", "ok",
            "service", "contract-format-service",
            "version", "1.0.0"
        ));
    }
}
