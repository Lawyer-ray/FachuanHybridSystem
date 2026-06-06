package com.fachuan.poi.service;

import com.fachuan.poi.enums.HeadingLevel;
import com.fachuan.poi.enums.NumberingType;
import com.fachuan.poi.enums.ParagraphType;
import com.fachuan.poi.model.ContractFormatConfig;
import com.fachuan.poi.model.DocumentStructure;
import com.fachuan.poi.model.DocumentStructure.DocumentNode;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.xwpf.usermodel.*;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTPageMar;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTPageSz;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTSectPr;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTNumbering;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTAbstractNum;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.STNumberFormat;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

/**
 * 合同格式化服务
 * 核心服务，负责合同文档的格式化处理
 */
@Service
@Slf4j
public class ContractFormatService {

    private final ParagraphClassifier classifier;

    public ContractFormatService(ParagraphClassifier classifier) {
        this.classifier = classifier;
    }

    /**
     * 格式化合同文档
     *
     * @param docxBytes 原始DOCX文件
     * @param config 格式配置
     * @return 格式化后的DOCX文件
     */
    public byte[] format(byte[] docxBytes, ContractFormatConfig config)
            throws IOException {

        long startTime = System.currentTimeMillis();

        try (XWPFDocument doc = new XWPFDocument(
                new ByteArrayInputStream(docxBytes))) {

            // 1. 标准化页边距
            normalizeMargins(doc, config);

            // 2. 设置自动编号（如果需要）
            if (config.isRenumberHeadings()) {
                setupAutoNumbering(doc, config.getNumberingType());
            }

            // 3. 提取文档结构
            DocumentStructure structure = extractStructure(doc);

            // 4. 重新编号（如果需要）
            if (config.isRenumberHeadings()) {
                renumberHeadings(structure);
            }

            // 5. 应用格式
            applyFormatting(doc, structure, config);

            // 6. 标准化表格
            if (config.isNormalizeTableBorders()) {
                normalizeAllTables(doc);
            }

            // 7. 转换为byte[]
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            doc.write(out);
            doc.close();

            long elapsed = System.currentTimeMillis() - startTime;
            log.info("合同格式化完成，耗时 {}ms，原始 {} bytes → {} bytes",
                elapsed, docxBytes.length, out.size());

            return out.toByteArray();
        }
    }

    /**
     * 提取文档结构
     */
    private DocumentStructure extractStructure(XWPFDocument doc) {
        DocumentStructure structure = new DocumentStructure();

        List<XWPFParagraph> paragraphs = doc.getParagraphs();
        for (int i = 0; i < paragraphs.size(); i++) {
            XWPFParagraph para = paragraphs.get(i);
            DocumentNode node = classifier.classifyAndBuildNode(para, i);
            structure.addNode(node);
        }

        // 统计标题数量
        structure.countHeadings();

        log.info("文档结构提取完成：{} 个节点，{} 个标题，最大层级 {}",
            structure.getNodeCount(),
            structure.getTotalHeadingCount(),
            structure.getMaxHeadingLevel());

        return structure;
    }

    /**
     * 重新编排序号
     */
    private void renumberHeadings(DocumentStructure structure) {
        int l1Count = 0, l2Count = 0, l3Count = 0;

        for (DocumentNode node : structure.getNodes()) {
            if (node.getLevel() == HeadingLevel.LEVEL_1) {
                l1Count++;
                l2Count = 0;  // 重置
                l3Count = 0;
                node.setNormalizedNumber(numberToChinese(l1Count) + "、");
            } else if (node.getLevel() == HeadingLevel.LEVEL_2) {
                l2Count++;
                l3Count = 0;  // 重置
                node.setNormalizedNumber(l2Count + ".");
            } else if (node.getLevel() == HeadingLevel.LEVEL_3) {
                l3Count++;
                node.setNormalizedNumber("(" + l3Count + ")");
            }
        }

        log.info("重新编号完成：一级标题 {} 个，二级标题 {} 个，三级标题 {} 个",
            l1Count, l2Count, l3Count);
    }

    /**
     * 应用格式
     */
    private void applyFormatting(
            XWPFDocument doc,
            DocumentStructure structure,
            ContractFormatConfig config) {

        List<XWPFParagraph> paragraphs = doc.getParagraphs();

        for (DocumentNode node : structure.getNodes()) {
            if (node.getIndex() >= paragraphs.size()) {
                continue;
            }

            XWPFParagraph para = paragraphs.get(node.getIndex());
            applyParagraphFormatting(para, node, config);
        }
    }

    /**
     * 应用段落格式
     */
    private void applyParagraphFormatting(
            XWPFParagraph para,
            DocumentNode node,
            ContractFormatConfig config) {

        // 1. 设置行距
        para.setSpacingBefore(0);
        para.setSpacingAfter(0);
        // 使用CTPPr设置行距（18pt = 360 twips）
        org.openxmlformats.schemas.wordprocessingml.x2006.main.CTPPr pPr =
            para.getCTP().addNewPPr();
        pPr.addNewSpacing().setLine(BigInteger.valueOf(config.getLineSpacing()));

        // 2. 根据类型应用格式
        switch (node.getType()) {
            case TITLE:
                para.setAlignment(config.getTitleAlignment());
                para.setFirstLineIndent(0);
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getTitleFont(),
                        config.getTitleFontSize(),
                        true);
                }
                break;

            case HEADING_L1:
                para.setAlignment(ParagraphAlignment.LEFT);
                para.setFirstLineIndent(0);
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getHeadingL1Font(),
                        config.getHeadingL1FontSize(),
                        true);
                }
                break;

            case HEADING_L2:
                para.setAlignment(ParagraphAlignment.LEFT);
                para.setFirstLineIndent(0);
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getHeadingL2Font(),
                        config.getHeadingL2FontSize(),
                        true);
                }
                break;

            case HEADING_L3:
                para.setAlignment(ParagraphAlignment.LEFT);
                para.setFirstLineIndent(0);
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getHeadingL3Font(),
                        config.getHeadingL3FontSize(),
                        true);
                }
                break;

            case CLAUSE:
                para.setAlignment(ParagraphAlignment.LEFT);
                para.setFirstLineIndent(0);
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getClauseFont(),
                        config.getClauseFontSize(),
                        true);
                }
                break;

            case BODY:
                para.setAlignment(config.getBodyAlignment());
                para.setFirstLineIndent(config.getFirstLineIndent());
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getBodyFont(),
                        config.getBodyFontSize(),
                        false);
                }
                break;

            case SIGNATURE:
                para.setAlignment(ParagraphAlignment.LEFT);
                para.setFirstLineIndent(0);
                for (XWPFRun run : para.getRuns()) {
                    normalizeRun(run,
                        config.getBodyFont(),
                        config.getBodyFontSize(),
                        false);
                }
                break;

            case TABLE:
            case OTHER:
            default:
                // 保持原样或应用默认格式
                break;
        }
    }

    /**
     * 标准化Run格式
     */
    private void normalizeRun(
            XWPFRun run,
            String fontFamily,
            int fontSize,
            boolean bold) {

        run.setFontFamily(fontFamily);
        run.setFontSize(fontSize);
        run.setBold(bold);
        run.setColor("000000");  // 黑色

        // 保留斜体、下划线等强调格式（如果需要）
        // 不覆盖这些格式，只标准化字体和字号
    }

    /**
     * 标准化页边距
     */
    private void normalizeMargins(XWPFDocument doc, ContractFormatConfig config) {
        CTSectPr sectPr = doc.getDocument().getBody().addNewSectPr();

        // 页面尺寸（A4）
        CTPageSz pageSz = sectPr.addNewPgSz();
        pageSz.setW(BigInteger.valueOf(11906));  // 210mm
        pageSz.setH(BigInteger.valueOf(16838));  // 297mm

        // 页边距
        CTPageMar pageMar = sectPr.addNewPgMar();
        pageMar.setTop(BigInteger.valueOf(config.getMarginTop()));
        pageMar.setBottom(BigInteger.valueOf(config.getMarginBottom()));
        pageMar.setLeft(BigInteger.valueOf(config.getMarginLeft()));
        pageMar.setRight(BigInteger.valueOf(config.getMarginRight()));
    }

    /**
     * 设置自动编号
     * 注意：Word自动编号域的设置比较复杂，这里简化处理
     * 实际的自动编号需要在Word中手动设置或使用更复杂的API
     */
    private void setupAutoNumbering(XWPFDocument doc, NumberingType numberingType) {
        // 简化实现：记录日志，实际的自动编号需要在Word文档中设置
        log.info("自动编号类型设置为：{}（需要在Word中手动应用编号样式）", numberingType.getDescription());
    }

    /**
     * 标准化所有表格
     */
    private void normalizeAllTables(XWPFDocument doc) {
        for (XWPFTable table : doc.getTables()) {
            normalizeTableBorders(table);
        }
    }

    /**
     * 标准化表格边框
     */
    private void normalizeTableBorders(XWPFTable table) {
        // 设置统一的单线边框
        org.openxmlformats.schemas.wordprocessingml.x2006.main.CTTblPr tblPr =
            table.getCTTbl().getTblPr();

        if (tblPr == null) {
            tblPr = table.getCTTbl().addNewTblPr();
        }

        org.openxmlformats.schemas.wordprocessingml.x2006.main.CTTblBorders borders =
            tblPr.getTblBorders();

        if (borders == null) {
            borders = tblPr.addNewTblBorders();
        }

        // 设置边框样式
        borders.addNewTop().setVal(
            org.openxmlformats.schemas.wordprocessingml.x2006.main.STBorder.SINGLE);
        borders.addNewBottom().setVal(
            org.openxmlformats.schemas.wordprocessingml.x2006.main.STBorder.SINGLE);
        borders.addNewLeft().setVal(
            org.openxmlformats.schemas.wordprocessingml.x2006.main.STBorder.SINGLE);
        borders.addNewRight().setVal(
            org.openxmlformats.schemas.wordprocessingml.x2006.main.STBorder.SINGLE);
        borders.addNewInsideH().setVal(
            org.openxmlformats.schemas.wordprocessingml.x2006.main.STBorder.SINGLE);
        borders.addNewInsideV().setVal(
            org.openxmlformats.schemas.wordprocessingml.x2006.main.STBorder.SINGLE);
    }

    /**
     * 数字转中文
     */
    private String numberToChinese(int number) {
        String[] chinese = {"一", "二", "三", "四", "五", "六", "七", "八", "九", "十"};
        if (number <= 10) {
            return chinese[number - 1];
        } else if (number < 20) {
            return "十" + chinese[number - 11];
        } else {
            return String.valueOf(number);
        }
    }
}
