package com.fachuan.poi.model;

import com.fachuan.poi.enums.HeadingLevel;
import com.fachuan.poi.enums.ParagraphType;
import lombok.Data;

import java.util.ArrayList;
import java.util.List;

/**
 * 文档结构模型
 * 表示合同文档的层级结构
 */
@Data
public class DocumentStructure {

    /**
     * 所有文档节点（扁平化）
     */
    private List<DocumentNode> nodes;

    /**
     * 总标题数
     */
    private int totalHeadingCount;

    /**
     * 最大层级
     */
    private int maxHeadingLevel;

    /**
     * 总段落数
     */
    private int totalParagraphCount;

    public DocumentStructure() {
        this.nodes = new ArrayList<>();
    }

    /**
     * 添加节点
     */
    public void addNode(DocumentNode node) {
        nodes.add(node);
        totalParagraphCount++;
    }

    /**
     * 获取节点数量
     */
    public int getNodeCount() {
        return nodes.size();
    }

    /**
     * 统计标题数量
     */
    public void countHeadings() {
        int count = 0;
        int maxLevel = 0;

        for (DocumentNode node : nodes) {
            if (node.getLevel() != null) {
                count++;
                if (node.getLevel().getLevel() > maxLevel) {
                    maxLevel = node.getLevel().getLevel();
                }
            }
        }

        this.totalHeadingCount = count;
        this.maxHeadingLevel = maxLevel;
    }

    /**
     * 文档节点
     */
    @Data
    public static class DocumentNode {

        /**
         * 原始索引
         */
        private int index;

        /**
         * 段落类型
         */
        private ParagraphType type;

        /**
         * 标题层级（仅对标题有效）
         */
        private HeadingLevel level;

        /**
         * 原始编号（如"一、"、"1."）
         */
        private String originalNumber;

        /**
         * 标准化编号（如"第一条"、"1."）
         */
        private String normalizedNumber;

        /**
         * 文本内容
         */
        private String text;

        /**
         * 是否有编号
         */
        private boolean isNumbered;

        /**
         * 缩进层级
         */
        private int indentLevel;

        /**
         * 字体大小（half-points）
         */
        private double fontSize;

        /**
         * 是否加粗
         */
        private boolean isBold;

        /**
         * 对齐方式
         */
        private String alignment;

        /**
         * 原始段落（用于后续格式化）
         */
        private transient Object originalParagraph;

        public DocumentNode() {
            this.isNumbered = false;
            this.indentLevel = 0;
        }
    }
}
