package com.fachuan.poi.model;

import com.fachuan.poi.enums.NumberingType;
import lombok.Data;
import org.apache.poi.xwpf.usermodel.ParagraphAlignment;

/**
 * 合同格式配置
 * 定义合同文档的格式化规则
 */
@Data
public class ContractFormatConfig {

    // ========== 编号配置 ==========

    /**
     * 编号类型
     * CHINESE: 一、→1.→(1)
     * DIGITAL: 1.→1.1.→1.1.1.
     */
    private NumberingType numberingType = NumberingType.CHINESE;

    // ========== 行距配置 ==========

    /**
     * 行距（twips）
     * 18pt = 360 twips
     */
    private int lineSpacing = 360;

    // ========== 缩进配置 ==========

    /**
     * 首行缩进（twips）
     * 2字符 = 480 twips
     */
    private int firstLineIndent = 480;

    /**
     * 左缩进（twips）
     */
    private int leftIndent = 0;

    // ========== 字体配置（正文）==========

    /**
     * 正文字体
     */
    private String bodyFont = "宋体";

    /**
     * 正文字号（half-points）
     * 12pt = 24 half-points
     */
    private int bodyFontSize = 24;

    // ========== 字体配置（一级标题）==========

    /**
     * 一级标题字体
     */
    private String headingL1Font = "黑体";

    /**
     * 一级标题字号（half-points）
     * 18pt = 36 half-points
     */
    private int headingL1FontSize = 36;

    // ========== 字体配置（二级标题）==========

    /**
     * 二级标题字体
     */
    private String headingL2Font = "黑体";

    /**
     * 二级标题字号（half-points）
     * 14pt = 28 half-points
     */
    private int headingL2FontSize = 28;

    // ========== 字体配置（三级标题）==========

    /**
     * 三级标题字体
     */
    private String headingL3Font = "宋体";

    /**
     * 三级标题字号（half-points）
     * 12pt = 24 half-points
     */
    private int headingL3FontSize = 24;

    // ========== 字体配置（条款）==========

    /**
     * 条款字体
     */
    private String clauseFont = "黑体";

    /**
     * 条款字号（half-points）
     * 12pt = 24 half-points
     */
    private int clauseFontSize = 24;

    // ========== 字体配置（标题）==========

    /**
     * 标题字体
     */
    private String titleFont = "黑体";

    /**
     * 标题字号（half-points）
     * 22pt = 44 half-points
     */
    private int titleFontSize = 44;

    // ========== 对齐配置 ==========

    /**
     * 正文对齐方式
     */
    private ParagraphAlignment bodyAlignment = ParagraphAlignment.BOTH;

    /**
     * 标题对齐方式
     */
    private ParagraphAlignment titleAlignment = ParagraphAlignment.CENTER;

    // ========== 页边距配置（A4标准）==========

    /**
     * 上边距（twips）
     * 2.54cm = 1440 twips
     */
    private int marginTop = 1440;

    /**
     * 下边距（twips）
     * 2.54cm = 1440 twips
     */
    private int marginBottom = 1440;

    /**
     * 左边距（twips）
     * 3.17cm = 1800 twips
     */
    private int marginLeft = 1800;

    /**
     * 右边距（twips）
     * 3.17cm = 1800 twips
     */
    private int marginRight = 1800;

    // ========== 表格配置 ==========

    /**
     * 是否标准化表格边框
     */
    private boolean normalizeTableBorders = true;

    // ========== 其他配置 ==========

    /**
     * 是否保留强调格式（斜体、下划线等）
     */
    private boolean preserveEmphasis = true;

    /**
     * 是否重新编排序号
     */
    private boolean renumberHeadings = true;

    /**
     * 默认配置（符合验收标准）
     */
    public static ContractFormatConfig defaultConfig() {
        return new ContractFormatConfig();
    }

    /**
     * 快速配置（最小化修改）
     */
    public static ContractFormatConfig minimalConfig() {
        ContractFormatConfig config = new ContractFormatConfig();
        config.setFirstLineIndent(0);  // 不修改缩进
        config.setRenumberHeadings(false);  // 不重新编号
        return config;
    }
}
