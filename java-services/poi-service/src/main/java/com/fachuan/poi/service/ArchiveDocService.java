package com.fachuan.poi.service;

import com.fachuan.poi.model.ArchiveRequest;
import com.fachuan.poi.util.DocxHelper;
import org.apache.poi.xwpf.usermodel.ParagraphAlignment;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.apache.poi.xwpf.usermodel.XWPFTableRow;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;

/**
 * 归档文书生成服务 — 案卷封面、结案归档登记表、卷内目录.
 * Uses POI to generate higher-quality DOCX than docxtpl:
 * - Styled tables with proper column widths and borders
 * - Precise paragraph formatting (Chinese legal document standards)
 * - Dynamic table row insertion with alternating backgrounds
 * - Professional header/footer layout
 */
@Service
public class ArchiveDocService {

    // ══════════════════════════════════════════════════════════════════════
    // 1. 案卷封面 (Case Folder Cover)
    // ══════════════════════════════════════════════════════════════════════

    public byte[] generateCaseCover(ArchiveRequest req) throws IOException {
        XWPFDocument doc = new XWPFDocument();
        DocxHelper.setA4Defaults(doc);

        // ── Title block ──
        addSpacer(doc, 6);

        XWPFParagraph title = doc.createParagraph();
        title.setAlignment(ParagraphAlignment.CENTER);
        title.setSpacingAfter(400);
        XWPFRun titleRun = title.createRun();
        titleRun.setText("案  卷  封  面");
        titleRun.setBold(true);
        titleRun.setFontSize(36);
        titleRun.setFontFamily("方正小标宋简体");
        titleRun.setColor("000000");

        addSpacer(doc, 2);

        // ── Info table (form-style, 2 columns) ──
        String[][] coverData = {
            {"案件名称", req.getCaseName()},
            {"案件类型", req.getCaseType()},
            {"案    号", req.getCaseNumber()},
            {"案    由", req.getCauseOfAction()},
            {"管辖法院", req.getCourtName()},
            {"我方当事人", req.getOurPartyName()},
            {"对方当事人", req.getOpposingPartyName()},
            {"主办律师", req.getLeadLawyer()},
            {"案件阶段", req.getCaseStage()},
            {"审理结果", req.getTrialResult()},
            {"OA编号", req.getOaCaseNumber()},
            {"开始日期", req.getStartDate()},
            {"归档日期", req.getArchiveDate()},
        };

        XWPFTable table = doc.createTable(coverData.length, 2);

        for (int r = 0; r < coverData.length; r++) {
            XWPFTableRow row = table.getRow(r);

            // Label cell
            XWPFTableCell labelCell = row.getCell(0);
            labelCell.removeParagraph(0);
            XWPFParagraph lp = labelCell.addParagraph();
            lp.setAlignment(ParagraphAlignment.RIGHT);
            XWPFRun lr = lp.createRun();
            lr.setText(coverData[r][0]);
            lr.setBold(true);
            lr.setFontFamily("黑体");
            lr.setFontSize(14);

            // Value cell
            XWPFTableCell valueCell = row.getCell(1);
            valueCell.removeParagraph(0);
            XWPFParagraph vp = valueCell.addParagraph();
            XWPFRun vr = vp.createRun();
            vr.setText(coverData[r][1] != null ? coverData[r][1] : "/");
            vr.setFontFamily("仿宋");
            vr.setFontSize(14);

            // Alternate row background
            if (r % 2 == 0) {
                labelCell.setColor("F5F5F5");
                valueCell.setColor("F5F5F5");
            }
        }

        addSpacer(doc, 4);

        // Bottom: archive date
        XWPFParagraph bottom = doc.createParagraph();
        bottom.setAlignment(ParagraphAlignment.RIGHT);
        XWPFRun bottomRun = bottom.createRun();
        bottomRun.setText("归档日期：" + (req.getArchiveDate() != null ? req.getArchiveDate() : "/"));
        bottomRun.setFontFamily("仿宋");
        bottomRun.setFontSize(12);

        return toBytes(doc);
    }

    // ══════════════════════════════════════════════════════════════════════
    // 2. 结案归档登记表 (Closing Archive Registration Form)
    // ══════════════════════════════════════════════════════════════════════

    public byte[] generateClosingRegister(ArchiveRequest req) throws IOException {
        XWPFDocument doc = new XWPFDocument();
        DocxHelper.setA4Defaults(doc);

        // Header
        DocxHelper.addHeader(doc, req.getOaCaseNumber() + " | 结案归档登记表");

        // Title
        XWPFParagraph title = doc.createParagraph();
        title.setAlignment(ParagraphAlignment.CENTER);
        title.setSpacingAfter(300);
        XWPFRun tr = title.createRun();
        tr.setText("结 案 归 档 登 记 表");
        tr.setBold(true);
        tr.setFontSize(22);
        tr.setFontFamily("黑体");

        // Basic info table
        String[][] basicInfo = {
            {"合同名称", req.getContractName()},
            {"我方当事人", req.getOurPartyName()},
            {"合同类型", req.getContractType()},
            {"主办律师", req.getLeadLawyer()},
            {"OA案件编号", req.getOaCaseNumber()},
            {"年    份", req.getYear()},
        };

        XWPFTable basicTable = doc.createTable(basicInfo.length, 2);
        for (int r = 0; r < basicInfo.length; r++) {
            XWPFTableRow row = basicTable.getRow(r);
            // Label
            XWPFTableCell lc = row.getCell(0);
            lc.removeParagraph(0);
            XWPFRun lr = lc.addParagraph().createRun();
            lr.setText(basicInfo[r][0]);
            lr.setBold(true);
            lr.setFontFamily("黑体");
            lr.setFontSize(11);
            // Value
            XWPFTableCell vc = row.getCell(1);
            vc.removeParagraph(0);
            XWPFRun vr = vc.addParagraph().createRun();
            vr.setText(basicInfo[r][1] != null ? basicInfo[r][1] : "/");
            vr.setFontFamily("仿宋");
            vr.setFontSize(11);
        }

        doc.createParagraph().setSpacingAfter(200);

        // Archive materials checklist table
        XWPFParagraph checklistTitle = doc.createParagraph();
        XWPFRun ctr = checklistTitle.createRun();
        ctr.setText("归档材料清单");
        ctr.setBold(true);
        ctr.setFontFamily("黑体");
        ctr.setFontSize(14);

        List<ArchiveRequest.ArchiveItem> items = req.getArchiveItems();
        if (items != null && !items.isEmpty()) {
            XWPFTable checklist = doc.createTable(items.size() + 1, 4);
            // Header row
            String[] headers = {"序号", "材料名称", "页码", "备注"};
            XWPFTableRow headerRow = checklist.getRow(0);
            for (int i = 0; i < headers.length; i++) {
                XWPFTableCell cell = headerRow.getCell(i);
                cell.setColor("2E75B6");
                cell.removeParagraph(0);
                XWPFRun hr = cell.addParagraph().createRun();
                hr.setText(headers[i]);
                hr.setBold(true);
                hr.setColor("FFFFFF");
                hr.setFontFamily("微软雅黑");
                hr.setFontSize(10);
            }
            // Data rows
            for (int r = 0; r < items.size(); r++) {
                ArchiveRequest.ArchiveItem item = items.get(r);
                XWPFTableRow dataRow = checklist.getRow(r + 1);
                String[] values = {
                    String.valueOf(r + 1),
                    item.getName(),
                    item.getPages() != null ? item.getPages() : "/",
                    item.getNote() != null ? item.getNote() : ""
                };
                for (int c = 0; c < 4; c++) {
                    XWPFTableCell cell = dataRow.getCell(c);
                    cell.removeParagraph(0);
                    XWPFRun dr = cell.addParagraph().createRun();
                    dr.setText(values[c]);
                    dr.setFontFamily("宋体");
                    dr.setFontSize(10);
                    if (r % 2 == 1) cell.setColor("F5F5F5");
                }
            }
        }

        return toBytes(doc);
    }

    // ══════════════════════════════════════════════════════════════════════
    // 3. 卷内目录 (Folder Contents Table of Contents)
    // ══════════════════════════════════════════════════════════════════════

    public byte[] generateCatalog(ArchiveRequest req) throws IOException {
        XWPFDocument doc = new XWPFDocument();
        DocxHelper.setA4Defaults(doc);

        // Header with page numbers
        DocxHelper.addHeader(doc, req.getOaCaseNumber() + " | 卷内目录");
        DocxHelper.addFooterWithPageNumber(doc);

        // Title
        XWPFParagraph title = doc.createParagraph();
        title.setAlignment(ParagraphAlignment.CENTER);
        title.setSpacingAfter(200);
        XWPFRun tr = title.createRun();
        tr.setText("卷  内  目  录");
        tr.setBold(true);
        tr.setFontSize(22);
        tr.setFontFamily("黑体");

        // Metadata line
        XWPFParagraph meta = doc.createParagraph();
        meta.setAlignment(ParagraphAlignment.LEFT);
        XWPFRun metaRun = meta.createRun();
        metaRun.setText("主办律师：" + nn(req.getLeadLawyer())
                + "　　归档日期：" + nn(req.getArchiveDate())
                + "　　OA编号：" + nn(req.getOaCaseNumber()));
        metaRun.setFontFamily("宋体");
        metaRun.setFontSize(10);
        metaRun.setColor("666666");

        doc.createParagraph().setSpacingAfter(100);

        // Catalog table
        List<ArchiveRequest.CatalogEntry> entries = req.getCatalogEntries();
        if (entries != null && !entries.isEmpty()) {
            XWPFTable catalog = doc.createTable(entries.size() + 1, 3);
            String[] headers = {"序号", "材料名称", "页码"};
            XWPFTableRow headerRow = catalog.getRow(0);
            for (int i = 0; i < headers.length; i++) {
                XWPFTableCell cell = headerRow.getCell(i);
                cell.setColor("1F4E79");
                cell.removeParagraph(0);
                XWPFRun hr = cell.addParagraph().createRun();
                hr.setText(headers[i]);
                hr.setBold(true);
                hr.setColor("FFFFFF");
                hr.setFontFamily("微软雅黑");
                hr.setFontSize(10);
            }
            for (int r = 0; r < entries.size(); r++) {
                ArchiveRequest.CatalogEntry entry = entries.get(r);
                XWPFTableRow dataRow = catalog.getRow(r + 1);
                String[] values = {
                    entry.getSequenceNumber(),
                    entry.getMaterialName(),
                    entry.getPageNumbers()
                };
                for (int c = 0; c < 3; c++) {
                    XWPFTableCell cell = dataRow.getCell(c);
                    cell.removeParagraph(0);
                    XWPFRun dr = cell.addParagraph().createRun();
                    dr.setText(values[c] != null ? values[c] : "/");
                    dr.setFontFamily("宋体");
                    dr.setFontSize(10);
                    if (r % 2 == 1) cell.setColor("F5F5F5");
                }
            }
        } else {
            XWPFParagraph empty = doc.createParagraph();
            empty.setAlignment(ParagraphAlignment.CENTER);
            XWPFRun er = empty.createRun();
            er.setText("（暂无归档材料记录）");
            er.setFontFamily("宋体");
            er.setFontSize(12);
            er.setColor("999999");
            er.setItalic(true);
        }

        return toBytes(doc);
    }

    // ── Helpers ──

    private void addSpacer(XWPFDocument doc, int lines) {
        for (int i = 0; i < lines; i++) {
            doc.createParagraph();
        }
    }

    private String nn(String s) {
        return s != null && !s.isEmpty() ? s : "/";
    }

    private byte[] toBytes(XWPFDocument doc) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        doc.write(baos);
        doc.close();
        return baos.toByteArray();
    }
}
