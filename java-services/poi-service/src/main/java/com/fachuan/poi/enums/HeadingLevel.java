package com.fachuan.poi.enums;

/**
 * 标题层级枚举
 * 表示合同文档中标题的层级关系
 */
public enum HeadingLevel {

    LEVEL_1(1, "一级", "一、二、三、"),
    LEVEL_2(2, "二级", "1. 2. 3."),
    LEVEL_3(3, "三级", "(1) (2) (3)");

    private final int level;
    private final String description;
    private final String example;

    HeadingLevel(int level, String description, String example) {
        this.level = level;
        this.description = description;
        this.example = example;
    }

    public int getLevel() {
        return level;
    }

    public String getDescription() {
        return description;
    }

    public String getExample() {
        return example;
    }

    /**
     * 根据层级数获取枚举
     */
    public static HeadingLevel fromLevel(int level) {
        for (HeadingLevel headingLevel : values()) {
            if (headingLevel.level == level) {
                return headingLevel;
            }
        }
        return null;
    }
}
