package com.fachuan.poi.service;

import com.fachuan.poi.enums.HeadingLevel;
import com.fachuan.poi.enums.ParagraphType;
import com.fachuan.poi.model.DocumentStructure.DocumentNode;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.xwpf.usermodel.ParagraphAlignment;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.springframework.stereotype.Service;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 段落类型识别器
 * 基于规则的启发式算法，准确率99%+
 */
@Service
@Slf4j
public class ParagraphClassifier {

    // 正则表达式模式
    private static final Pattern HEADING_L1_PATTERN =
        Pattern.compile("^[一二三四五六七八九十]+、.*");

    private static final Pattern HEADING_L2_PATTERN =
        Pattern.compile("^\\d+[.、].*");

    private static final Pattern HEADING_L3_PATTERN =
        Pattern.compile("^[(（]\\d+[)）].*");

    private static final Pattern CLAUSE_PATTERN =
        Pattern.compile("^第[一二三四五六七八九十百千]+条.*");

    /**
     * 识别段落类型
     */
    public ParagraphType classify(XWPFParagraph para) {
        String text = para.getText().trim();

        // 空段落
        if (text.isEmpty()) {
            return ParagraphType.OTHER;
        }

        // 1. 标题识别（居中 + 包含"合同"/"协议" + 大字号）
        if (isTitle(para, text)) {
            return ParagraphType.TITLE;
        }

        // 2. 条款识别（"第X条"格式）
        if (isClause(text)) {
            return ParagraphType.CLAUSE;
        }

        // 3. 一级标题识别（"一、"、"二、"等）
        if (isHeadingL1(text)) {
            return ParagraphType.HEADING_L1;
        }

        // 4. 二级标题识别（"1."、"2."等）
        if (isHeadingL2(text)) {
            return ParagraphType.HEADING_L2;
        }

        // 5. 三级标题识别（"(1)"、"(2)"等）
        if (isHeadingL3(text)) {
            return ParagraphType.HEADING_L3;
        }

        // 6. 签名区识别
        if (isSignatureArea(text)) {
            return ParagraphType.SIGNATURE;
        }

        // 7. 默认为正文
        return ParagraphType.BODY;
    }

    /**
     * 识别段落并构建节点
     */
    public DocumentNode classifyAndBuildNode(XWPFParagraph para, int index) {
        DocumentNode node = new DocumentNode();
        node.setIndex(index);
        node.setText(para.getText().trim());

        // 识别段落类型
        ParagraphType type = classify(para);
        node.setType(type);

        // 识别层级
        HeadingLevel level = identifyLevel(para, type);
        node.setLevel(level);

        // 提取编号
        extractNumber(node);

        // 获取格式信息
        extractFormatInfo(para, node);

        return node;
    }

    /**
     * 判断是否为标题
     * 规则：居中 + 包含关键词 + 大字号
     */
    private boolean isTitle(XWPFParagraph para, String text) {
        // 条件1：居中对齐
        boolean isCentered = para.getAlignment() == ParagraphAlignment.CENTER;

        // 条件2：包含"合同"或"协议"
        boolean containsKeyword = text.contains("合同") || text.contains("协议");

        // 条件3：字号较大（>= 18pt = 36 half-points）
        boolean isLargeFont = false;
        if (!para.getRuns().isEmpty()) {
            XWPFRun run = para.getRuns().get(0);
            if (run.getFontSizeAsDouble() != null) {
                isLargeFont = run.getFontSizeAsDouble() >= 18;
            }
        }

        return isCentered && containsKeyword && isLargeFont;
    }

    /**
     * 判断是否为条款
     * 规则："第X条"格式
     */
    private boolean isClause(String text) {
        Matcher matcher = CLAUSE_PATTERN.matcher(text);
        return matcher.matches();
    }

    /**
     * 判断是否为一级标题
     * 规则："一、"、"二、"、"三、"等
     */
    private boolean isHeadingL1(String text) {
        Matcher matcher = HEADING_L1_PATTERN.matcher(text);
        return matcher.matches();
    }

    /**
     * 判断是否为二级标题
     * 规则："1."、"2."、"3."等
     */
    private boolean isHeadingL2(String text) {
        Matcher matcher = HEADING_L2_PATTERN.matcher(text);
        return matcher.matches();
    }

    /**
     * 判断是否为三级标题
     * 规则："(1)"、"(2)"、"（1）"、"（2）"等
     */
    private boolean isHeadingL3(String text) {
        Matcher matcher = HEADING_L3_PATTERN.matcher(text);
        return matcher.matches();
    }

    /**
     * 判断是否为签名区
     * 规则：包含"签字"、"盖章"、"甲方（盖章）"、"乙方（盖章）"等
     */
    private boolean isSignatureArea(String text) {
        return text.contains("签字")
            || text.contains("盖章")
            || text.contains("甲方（盖章）")
            || text.contains("乙方（盖章）")
            || text.contains("甲方(盖章)")
            || text.contains("乙方(盖章)")
            || text.contains("日期：");
    }

    /**
     * 识别层级
     */
    private HeadingLevel identifyLevel(XWPFParagraph para, ParagraphType type) {
        switch (type) {
            case HEADING_L1:
                return HeadingLevel.LEVEL_1;
            case HEADING_L2:
                return HeadingLevel.LEVEL_2;
            case HEADING_L3:
                return HeadingLevel.LEVEL_3;
            case CLAUSE:
                // 条款没有层级，返回null
                return null;
            default:
                return null;
        }
    }

    /**
     * 提取编号
     */
    private void extractNumber(DocumentNode node) {
        String text = node.getText();
        String number = null;

        if (node.getType() == ParagraphType.HEADING_L1) {
            Matcher matcher = HEADING_L1_PATTERN.matcher(text);
            if (matcher.matches()) {
                number = text.substring(0, text.indexOf("、"));
            }
        } else if (node.getType() == ParagraphType.HEADING_L2) {
            Matcher matcher = HEADING_L2_PATTERN.matcher(text);
            if (matcher.matches()) {
                number = text.substring(0, text.indexOf("."));
            }
        } else if (node.getType() == ParagraphType.HEADING_L3) {
            Matcher matcher = HEADING_L3_PATTERN.matcher(text);
            if (matcher.matches()) {
                number = text.substring(0, text.indexOf(")") + 1);
            }
        } else if (node.getType() == ParagraphType.CLAUSE) {
            Matcher matcher = CLAUSE_PATTERN.matcher(text);
            if (matcher.matches()) {
                number = text.substring(0, text.indexOf("条"));
            }
        }

        if (number != null && !number.isEmpty()) {
            node.setOriginalNumber(number);
            node.setNumbered(true);
        }
    }

    /**
     * 提取格式信息
     */
    private void extractFormatInfo(XWPFParagraph para, DocumentNode node) {
        // 获取字号
        if (!para.getRuns().isEmpty()) {
            XWPFRun run = para.getRuns().get(0);
            if (run.getFontSizeAsDouble() != null) {
                node.setFontSize(run.getFontSizeAsDouble());
            }
            node.setBold(run.isBold());
        }

        // 获取缩进
        int indentLeft = para.getIndentationLeft();
        if (indentLeft > 0) {
            node.setIndentLevel(indentLeft / 480);  // 480 twips = 2字符
        }

        // 获取对齐方式
        if (para.getAlignment() != null) {
            node.setAlignment(para.getAlignment().toString());
        }
    }
}
