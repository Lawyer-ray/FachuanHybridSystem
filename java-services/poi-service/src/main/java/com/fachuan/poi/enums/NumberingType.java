package com.fachuan.poi.enums;

/**
 * 编号类型枚举
 * 支持两种多级编号格式
 */
public enum NumberingType {

    /**
     * 类型1：中文编号
     * 一、 → 1. → (1)
     */
    CHINESE("中文编号", "一、→1.→(1)"),

    /**
     * 类型2：数字编号
     * 1. → 1.1. → 1.1.1.
     */
    DIGITAL("数字编号", "1.→1.1.→1.1.1.");

    private final String description;
    private final String example;

    NumberingType(String description, String example) {
        this.description = description;
        this.example = example;
    }

    public String getDescription() {
        return description;
    }

    public String getExample() {
        return example;
    }

    /**
     * 从字符串解析编号类型
     */
    public static NumberingType fromString(String value) {
        if (value == null || value.isEmpty()) {
            return CHINESE;  // 默认使用中文编号
        }

        String lowerValue = value.toLowerCase();
        if (lowerValue.contains("digital") || lowerValue.contains("数字")) {
            return DIGITAL;
        }

        return CHINESE;
    }
}
