package com.fachuan.poi.enums;

/**
 * 段落类型枚举
 * 用于识别合同文档中的不同段落类型
 */
public enum ParagraphType {

    TITLE("标题", "合同标题，居中、加粗、黑体、44号"),

    HEADING_L1("一级标题", "一级标题，如：一、服务内容"),

    HEADING_L2("二级标题", "二级标题，如：1. 服务范围"),

    HEADING_L3("三级标题", "三级标题，如：(1) 具体服务"),

    CLAUSE("条款", "合同条款，如：第一条 服务期限"),

    BODY("正文", "正文内容"),

    SIGNATURE("签名区", "签名和盖章区域"),

    TABLE("表格", "表格内容"),

    OTHER("其他", "其他类型内容");

    private final String description;
    private final String example;

    ParagraphType(String description, String example) {
        this.description = description;
        this.example = example;
    }

    public String getDescription() {
        return description;
    }

    public String getExample() {
        return example;
    }
}
