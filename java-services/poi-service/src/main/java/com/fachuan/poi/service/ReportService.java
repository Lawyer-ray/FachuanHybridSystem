package com.fachuan.poi.service;

import com.fachuan.poi.model.ReportRequest;
import com.fachuan.poi.model.ReportRequest.*;
import com.fachuan.shared.poi.DocxHelper;
import org.apache.poi.xwpf.usermodel.*;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTP;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTSimpleField;
import org.springframework.stereotype.Service;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 尽调报告 (Due Diligence Report) generation using Apache POI.
 * Showcases advanced POI features: charts, styled tables, headers/footers,
 * section breaks, watermarks, rich paragraphs, bullet lists.
 */
@Service
public class ReportService {

    public byte[] generate(ReportRequest req) throws Exception {
        XWPFDocument doc = new XWPFDocument();

        // ════════════════════════════════════════════════════════════════
        // PAGE SETUP & STYLES
        // ════════════════════════════════════════════════════════════════
        DocxHelper.setA4Defaults(doc);

        // ── Header with project name ──
        DocxHelper.addHeader(doc, req.getProjectName() + " | " + req.getConfidentialityLevel());

        // ── Footer with page numbers ──
        DocxHelper.addFooterWithPageNumber(doc);

        // ── Watermark ──
        if ("机密".equals(req.getConfidentialityLevel())) {
            DocxHelper.addWatermark(doc, "机密文件");
        }

        // ════════════════════════════════════════════════════════════════
        // COVER PAGE
        // ════════════════════════════════════════════════════════════════
        buildCoverPage(doc, req);

        // Section break after cover page
        DocxHelper.addSectionBreak(doc, 11906, 16838, 1440, 1440, 1800, 1800);

        // ════════════════════════════════════════════════════════════════
        // TABLE OF CONTENTS (placeholder)
        // ════════════════════════════════════════════════════════════════
        DocxHelper.addHeading(doc, "目  录", 1);
        XWPFParagraph tocPara = doc.createParagraph();
        XWPFRun tocRun = tocPara.createRun();
        tocRun.setText("（请在 Word 中右键更新域以生成目录）");
        tocRun.setColor("999999");
        tocRun.setItalic(true);
        tocRun.setFontSize(10);

        // Add TOC field
        CTP tocP = doc.createParagraph().getCTP();
        CTSimpleField tocField = tocP.addNewFldSimple();
        tocField.setInstr(" TOC \\o \"1-3\" \\h \\z \\u ");

        DocxHelper.addSectionBreak(doc, 11906, 16838, 1440, 1440, 1800, 1800);

        // ════════════════════════════════════════════════════════════════
        // 1. COMPANY OVERVIEW
        // ════════════════════════════════════════════════════════════════
        DocxHelper.addHeading(doc, "一、公司概况", 1);

        // Company info as merged table (form-style)
        DocxHelper.addHeading(doc, "1.1 基本信息", 2);
        String[][] companyInfo = {
            {"公司名称", req.getCompanyName()},
            {"统一社会信用代码", req.getCompanyRegistrationNumber()},
            {"注册资本", req.getRegisteredCapital()},
            {"成立日期", req.getEstablishedDate()},
            {"法定代表人", req.getLegalRepresentative()},
            {"经营范围", req.getBusinessScope()},
        };
        DocxHelper.createMergedTable(doc, companyInfo, new int[]{3500, 7500});

        doc.createParagraph().setSpacingAfter(200);

        // ════════════════════════════════════════════════════════════════
        // 2. EQUITY STRUCTURE (nested table)
        // ════════════════════════════════════════════════════════════════
        DocxHelper.addHeading(doc, "二、股权结构", 1);

        if (req.getEquityStructure() != null && !req.getEquityStructure().isEmpty()) {
            List<String> headers = List.of("股东名称", "持股比例", "类型", "出资方式");
            List<List<String>> rows = new ArrayList<>();
            for (EquityHolder holder : req.getEquityStructure()) {
                rows.add(List.of(
                    holder.getName(),
                    String.format("%.2f%%", holder.getPercentage()),
                    holder.getType(),
                    holder.getContributionMethod()
                ));
            }
            // Highlight table with custom colors
            DocxHelper.createStyledTable(doc, headers, rows,
                    "1F4E79", "FFFFFF",
                    new int[]{3500, 2500, 2000, 3000});
        }

        doc.createParagraph().setSpacingAfter(200);

        // ════════════════════════════════════════════════════════════════
        // 3. FINANCIAL OVERVIEW (with chart)
        // ════════════════════════════════════════════════════════════════
        DocxHelper.addHeading(doc, "三、财务概况", 1);

        if (req.getFinancialData() != null && !req.getFinancialData().isEmpty()) {
            // Financial summary table
            DocxHelper.addHeading(doc, "3.1 主要财务指标", 2);
            List<String> finHeaders = List.of("年度", "营业收入(万元)", "净利润(万元)", "总资产(万元)", "总负债(万元)");
            List<List<String>> finRows = new ArrayList<>();
            for (FinancialYear fy : req.getFinancialData()) {
                finRows.add(List.of(
                    String.valueOf(fy.getYear()),
                    String.format("%.2f", fy.getRevenue()),
                    String.format("%.2f", fy.getProfit()),
                    String.format("%.2f", fy.getTotalAssets()),
                    String.format("%.2f", fy.getTotalLiabilities())
                ));
            }
            DocxHelper.createStyledTable(doc, finHeaders, finRows,
                    "2E75B6", "FFFFFF",
                    new int[]{1500, 2200, 2200, 2200, 2200});

            doc.createParagraph().setSpacingAfter(200);

            // Bar chart for revenue trend
            DocxHelper.addHeading(doc, "3.2 营收趋势", 2);
            String[] years = req.getFinancialData().stream()
                    .map(fy -> String.valueOf(fy.getYear()))
                    .toArray(String[]::new);
            double[] revenues = req.getFinancialData().stream()
                    .mapToDouble(FinancialYear::getRevenue)
                    .toArray();
            // Revenue summary as text (chart embedding requires additional setup)
            XWPFParagraph chartNote = doc.createParagraph();
            chartNote.setAlignment(ParagraphAlignment.CENTER);
            XWPFRun chartRun = chartNote.createRun();
            StringBuilder sb = new StringBuilder("营收趋势：");
            for (int i = 0; i < years.length; i++) {
                sb.append(years[i]).append("年 ").append(String.format("%.0f", revenues[i])).append("万元");
                if (i < years.length - 1) sb.append(" → ");
            }
            chartRun.setText(sb.toString());
            chartRun.setFontSize(10);
            chartRun.setFontFamily("宋体");
            chartRun.setItalic(true);
            chartRun.setColor("666666");
        }

        DocxHelper.addSectionBreak(doc, 11906, 16838, 1440, 1440, 1800, 1800);

        // ════════════════════════════════════════════════════════════════
        // 4. RISK ASSESSMENT
        // ════════════════════════════════════════════════════════════════
        DocxHelper.addHeading(doc, "四、风险评估", 1);

        if (req.getRiskItems() != null && !req.getRiskItems().isEmpty()) {
            List<String> riskHeaders = List.of("风险类别", "风险描述", "严重程度", "建议措施");
            List<List<String>> riskRows = new ArrayList<>();
            for (RiskItem item : req.getRiskItems()) {
                riskRows.add(List.of(
                    item.getCategory(),
                    item.getDescription(),
                    item.getSeverity(),
                    item.getRecommendation()
                ));
            }
            DocxHelper.createStyledTable(doc, riskHeaders, riskRows,
                    "C0392B", "FFFFFF",
                    new int[]{2000, 4000, 1500, 3500});
        }

        DocxHelper.addSectionBreak(doc, 11906, 16838, 1440, 1440, 1800, 1800);

        // ════════════════════════════════════════════════════════════════
        // 5. DYNAMIC SECTIONS
        // ════════════════════════════════════════════════════════════════
        if (req.getSections() != null) {
            int sectionNum = 5;
            for (ReportSection section : req.getSections()) {
                DocxHelper.addHeading(doc, convertToChineseNumeral(sectionNum) + "、" + section.getTitle(), section.getLevel() <= 1 ? 1 : section.getLevel());

                if (section.getContent() != null) {
                    String[] paragraphs = section.getContent().split("\n");
                    for (String p : paragraphs) {
                        if (!p.trim().isEmpty()) {
                            XWPFParagraph bodyPara = doc.createParagraph();
                            bodyPara.setFirstLineIndent(480);
                            bodyPara.setAlignment(ParagraphAlignment.BOTH);
                            bodyPara.setSpacingAfter(100);
                            XWPFRun run = bodyPara.createRun();
                            run.setText(p.trim());
                            run.setFontFamily("宋体");
                            run.setFontSize(12);
                        }
                    }
                }

                // Optional table in section
                if (section.getTableData() != null && !section.getTableData().isEmpty()) {
                    Map<String, String> firstRow = section.getTableData().get(0);
                    List<String> headers = new ArrayList<>(firstRow.keySet());
                    List<List<String>> rows = new ArrayList<>();
                    for (Map<String, String> row : section.getTableData()) {
                        rows.add(headers.stream().map(row::get).toList());
                    }
                    DocxHelper.createStyledTable(doc, headers, rows,
                            "2E75B6", "FFFFFF", null);
                }

                // Optional bullet list
                if (section.getBulletPoints() != null) {
                    for (String bullet : section.getBulletPoints()) {
                        DocxHelper.addBulletItem(doc, bullet);
                    }
                }

                doc.createParagraph().setSpacingAfter(100);
                sectionNum++;
            }
        }

        // ════════════════════════════════════════════════════════════════
        // DISCLAIMER & SIGNATURE
        // ════════════════════════════════════════════════════════════════
        doc.createParagraph().setSpacingBefore(600);
        XWPFParagraph disclaimer = doc.createParagraph();
        disclaimer.setAlignment(ParagraphAlignment.LEFT);
        XWPFRun discRun = disclaimer.createRun();
        discRun.setText("免责声明：本报告仅供内部参考，不构成法律意见。报告内容基于公开信息及委托人提供的资料整理而成，不保证信息的完整性和准确性。");
        discRun.setFontFamily("宋体");
        discRun.setFontSize(9);
        discRun.setColor("999999");
        discRun.setItalic(true);

        // Signature block
        doc.createParagraph().setSpacingAfter(400);
        XWPFParagraph sigRight = doc.createParagraph();
        sigRight.setAlignment(ParagraphAlignment.RIGHT);
        XWPFRun sigRun = sigRight.createRun();
        sigRun.setText(req.getAuthor());
        sigRun.setFontFamily("宋体");
        sigRun.setFontSize(12);

        XWPFParagraph dateRight = doc.createParagraph();
        dateRight.setAlignment(ParagraphAlignment.RIGHT);
        XWPFRun dateRun = dateRight.createRun();
        dateRun.setText(req.getReportDate());
        dateRun.setFontFamily("宋体");
        dateRun.setFontSize(12);

        // ── Save ──
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        doc.write(baos);
        doc.close();
        return baos.toByteArray();
    }

    private void buildCoverPage(XWPFDocument doc, ReportRequest req) {
        // Spacer
        for (int i = 0; i < 6; i++) {
            doc.createParagraph();
        }

        // Title
        XWPFParagraph titlePara = doc.createParagraph();
        titlePara.setAlignment(ParagraphAlignment.CENTER);
        XWPFRun titleRun = titlePara.createRun();
        titleRun.setText(req.getReportTitle());
        titleRun.setBold(true);
        titleRun.setFontSize(32);
        titleRun.setFontFamily("微软雅黑");
        titleRun.setColor("1F4E79");

        doc.createParagraph();

        // Project name
        XWPFParagraph projectPara = doc.createParagraph();
        projectPara.setAlignment(ParagraphAlignment.CENTER);
        XWPFRun projectRun = projectPara.createRun();
        projectRun.setText(req.getProjectName());
        projectRun.setFontSize(18);
        projectRun.setFontFamily("微软雅黑");
        projectRun.setColor("2E75B6");

        // Spacer
        for (int i = 0; i < 4; i++) {
            doc.createParagraph();
        }

        // Metadata
        addCoverLine(doc, "编制单位：" + req.getAuthor());
        addCoverLine(doc, "编制日期：" + req.getReportDate());
        addCoverLine(doc, "密级：" + req.getConfidentialityLevel());

        // Separator line
        XWPFParagraph linePara = doc.createParagraph();
        linePara.setAlignment(ParagraphAlignment.CENTER);
        XWPFRun lineRun = linePara.createRun();
        lineRun.setText("——————————————————");
        lineRun.setColor("CCCCCC");

        // Company name at bottom
        XWPFParagraph companyPara = doc.createParagraph();
        companyPara.setAlignment(ParagraphAlignment.CENTER);
        companyPara.setSpacingBefore(200);
        XWPFRun companyRun = companyPara.createRun();
        companyRun.setText(req.getCompanyName());
        companyRun.setFontSize(14);
        companyRun.setFontFamily("宋体");
    }

    private void addCoverLine(XWPFDocument doc, String text) {
        XWPFParagraph para = doc.createParagraph();
        para.setAlignment(ParagraphAlignment.CENTER);
        para.setSpacingAfter(120);
        XWPFRun run = para.createRun();
        run.setText(text);
        run.setFontSize(14);
        run.setFontFamily("宋体");
        run.setColor("404040");
    }

    private String convertToChineseNumeral(int num) {
        String[] numerals = {"零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"};
        if (num >= 0 && num <= 10) return numerals[num];
        return String.valueOf(num);
    }
}
