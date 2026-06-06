package com.fachuan.poi.model;

import lombok.Data;

/**
 * 合同格式化请求
 */
@Data
public class ContractFormatRequest {

    /**
     * DOCX文件（Base64编码或字节数组）
     */
    private byte[] docxBytes;

    /**
     * 格式配置（可选，使用默认值）
     */
    private ContractFormatConfig config;

    /**
     * 输出文件名（可选）
     */
    private String outputFileName;

    /**
     * 格式化方法（可选）
     * poi: 使用POI服务
     * python: 使用Python（降级方案）
     * auto: 自动选择
     */
    private String formatMethod;
}
