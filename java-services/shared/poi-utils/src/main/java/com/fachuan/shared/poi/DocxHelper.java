package com.fachuan.shared.poi;

import org.apache.poi.util.Units;
import org.apache.poi.wp.usermodel.HeaderFooterType;
import org.apache.poi.xwpf.usermodel.ParagraphAlignment;
import org.apache.poi.xwpf.usermodel.UnderlinePatterns;
import org.apache.poi.xwpf.usermodel.XWPFFooter;
import org.apache.poi.xwpf.usermodel.XWPFHeader;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.apache.poi.xwpf.usermodel.XWPFTableRow;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTP;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTPPr;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTSectPr;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTSimpleField;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.STSectionMark;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigInteger;
import java.util.List;

/**
 * DOCX helper using POI high-level API only.
 * All OOXML low-level types are accessed via the high-level wrapper methods.
 */
public final class DocxHelper {

    private DocxHelper() {}

    // ══════════════════════════════════════════════════════════════════════
    // 1. PARAGRAPHS
    // ══════════════════════════════════════════════════════════════════════

    public static XWPFParagraph addHeading(XWPFDocument doc, String text, int level) {
        XWPFParagraph para = doc.createParagraph();
        try { para.setStyle("Heading" + level); } catch (Exception ignored) {}
        XWPFRun run = para.createRun();
        run.setText(text);
        run.setBold(true);
        run.setFontSize(level == 1 ? 22 : level == 2 ? 16 : 13);
        run.setFontFamily("微软雅黑");
        return para;
    }

    public static XWPFParagraph addRichParagraph(XWPFDocument doc, String... segments) {
        XWPFParagraph para = doc.createParagraph();
        para.setSpacingAfter(200);
        for (int i = 0; i < segments.length; i += 2) {
            XWPFRun run = para.createRun();
            run.setText(segments[i]);
            if (i + 1 < segments.length) {
                String s = segments[i + 1];
                if (s.contains("bold")) run.setBold(true);
                if (s.contains("italic")) run.setItalic(true);
                if (s.contains("underline")) run.setUnderline(UnderlinePatterns.SINGLE);
                if (s.startsWith("size:")) run.setFontSize(Integer.parseInt(s.substring(5)));
                if (s.startsWith("color:")) run.setColor(s.substring(6));
                if (s.startsWith("font:")) run.setFontFamily(s.substring(5));
            }
        }
        return para;
    }

    public static void addNumberedItem(XWPFDocument doc, String text, int number) {
        XWPFParagraph para = doc.createParagraph();
        XWPFRun run = para.createRun();
        run.setText(number + ". " + text);
        run.setFontFamily("宋体");
        run.setFontSize(12);
    }

    public static void addBulletItem(XWPFDocument doc, String text) {
        XWPFParagraph para = doc.createParagraph();
        XWPFRun run = para.createRun();
        run.setText("• " + text);
        run.setFontFamily("宋体");
        run.setFontSize(12);
    }

    // ══════════════════════════════════════════════════════════════════════
    // 2. TABLES
    // ══════════════════════════════════════════════════════════════════════

    public static XWPFTable createStyledTable(
            XWPFDocument doc, List<String> headers, List<List<String>> rows,
            String headerBgColor, String headerFontColor, int[] colWidths) {

        XWPFTable table = doc.createTable(rows.size() + 1, headers.size());

        // Header row
        XWPFTableRow headerRow = table.getRow(0);
        for (int i = 0; i < headers.size(); i++) {
            XWPFTableCell cell = headerRow.getCell(i);
            cell.setColor(headerBgColor);
            cell.removeParagraph(0);
            XWPFParagraph p = cell.addParagraph();
            p.setAlignment(ParagraphAlignment.CENTER);
            XWPFRun run = p.createRun();
            run.setText(headers.get(i));
            run.setBold(true);
            run.setColor(headerFontColor);
            run.setFontFamily("微软雅黑");
            run.setFontSize(11);
        }

        // Data rows
        for (int r = 0; r < rows.size(); r++) {
            XWPFTableRow dataRow = table.getRow(r + 1);
            for (int c = 0; c < headers.size(); c++) {
                XWPFTableCell cell = dataRow.getCell(c);
                String value = c < rows.get(r).size() ? rows.get(r).get(c) : "";
                cell.removeParagraph(0);
                XWPFParagraph p = cell.addParagraph();
                XWPFRun run = p.createRun();
                run.setText(value);
                run.setFontFamily("宋体");
                run.setFontSize(10);
                if (r % 2 == 1) cell.setColor("F2F2F2");
            }
        }
        return table;
    }

    public static XWPFTable createMergedTable(XWPFDocument doc, String[][] data, int[] colWidths) {
        int rows = data.length;
        int cols = colWidths.length;
        XWPFTable table = doc.createTable(rows, cols);
        for (int r = 0; r < rows; r++) {
            XWPFTableRow row = table.getRow(r);
            for (int c = 0; c < cols; c++) {
                XWPFTableCell cell = row.getCell(c);
                cell.removeParagraph(0);
                XWPFParagraph p = cell.addParagraph();
                if (data[r][c] != null) {
                    XWPFRun run = p.createRun();
                    run.setText(data[r][c]);
                    run.setFontFamily(c == 0 ? "黑体" : "宋体");
                    run.setFontSize(10);
                    if (c == 0) run.setBold(true);
                }
            }
        }
        return table;
    }

    // ══════════════════════════════════════════════════════════════════════
    // 3. HEADERS & FOOTERS
    // ══════════════════════════════════════════════════════════════════════

    public static void addHeader(XWPFDocument doc, String headerText) {
        XWPFHeader header = doc.createHeader(HeaderFooterType.DEFAULT);
        XWPFParagraph para = header.createParagraph();
        para.setAlignment(ParagraphAlignment.RIGHT);
        XWPFRun run = para.createRun();
        run.setText(headerText);
        run.setFontSize(8);
        run.setColor("999999");
        run.setFontFamily("微软雅黑");
    }

    public static void addFooterWithPageNumber(XWPFDocument doc) {
        XWPFFooter footer = doc.createFooter(HeaderFooterType.DEFAULT);
        XWPFParagraph para = footer.createParagraph();
        para.setAlignment(ParagraphAlignment.CENTER);

        XWPFRun r1 = para.createRun();
        r1.setText("第 ");
        r1.setFontSize(9);
        r1.setColor("666666");

        // PAGE field
        CTP p = para.getCTP();
        CTSimpleField pageField = p.addNewFldSimple();
        pageField.setInstr(" PAGE ");

        XWPFRun r2 = para.createRun();
        r2.setText(" 页 / 共 ");
        r2.setFontSize(9);
        r2.setColor("666666");

        CTSimpleField totalField = p.addNewFldSimple();
        totalField.setInstr(" NUMPAGES ");

        XWPFRun r3 = para.createRun();
        r3.setText(" 页");
        r3.setFontSize(9);
        r3.setColor("666666");
    }

    // ══════════════════════════════════════════════════════════════════════
    // 4. SECTION BREAKS
    // ══════════════════════════════════════════════════════════════════════

    public static void addSectionBreak(XWPFDocument doc) {
        XWPFParagraph para = doc.createParagraph();
        CTPPr pPr = para.getCTP().addNewPPr();
        CTSectPr sectPr = pPr.addNewSectPr();
        sectPr.addNewType().setVal(STSectionMark.Enum.forString("nextPage"));
    }

    public static void addSectionBreak(
            XWPFDocument doc, int pageWidth, int pageHeight,
            int top, int bottom, int left, int right) {
        XWPFParagraph para = doc.createParagraph();
        CTPPr pPr = para.getCTP().addNewPPr();
        CTSectPr sectPr = pPr.addNewSectPr();
        sectPr.addNewType().setVal(STSectionMark.Enum.forString("nextPage"));
        sectPr.addNewPgSz().setW(BigInteger.valueOf(pageWidth));
        sectPr.addNewPgSz().setH(BigInteger.valueOf(pageHeight));
        sectPr.addNewPgMar().setTop(BigInteger.valueOf(top));
        sectPr.addNewPgMar().setBottom(BigInteger.valueOf(bottom));
        sectPr.addNewPgMar().setLeft(BigInteger.valueOf(left));
        sectPr.addNewPgMar().setRight(BigInteger.valueOf(right));
    }

    // ══════════════════════════════════════════════════════════════════════
    // 5. WATERMARK
    // ══════════════════════════════════════════════════════════════════════

    public static void addWatermark(XWPFDocument doc, String text) {
        XWPFHeader header = doc.createHeader(HeaderFooterType.DEFAULT);
        XWPFParagraph para = header.createParagraph();
        XWPFRun run = para.createRun();
        run.setText(text);
        run.setFontSize(48);
        run.setColor("E0E0E0");
        run.setItalic(true);
        run.setFontFamily("微软雅黑");
    }

    // ══════════════════════════════════════════════════════════════════════
    // 6. PAGE PROPERTIES
    // ══════════════════════════════════════════════════════════════════════

    public static void setA4Defaults(XWPFDocument doc) {
        CTSectPr sectPr = doc.getDocument().getBody().addNewSectPr();
        sectPr.addNewPgSz().setW(BigInteger.valueOf(11906));
        sectPr.addNewPgSz().setH(BigInteger.valueOf(16838));
        sectPr.addNewPgMar().setTop(BigInteger.valueOf(1440));
        sectPr.addNewPgMar().setBottom(BigInteger.valueOf(1440));
        sectPr.addNewPgMar().setLeft(BigInteger.valueOf(1800));
        sectPr.addNewPgMar().setRight(BigInteger.valueOf(1800));
        sectPr.addNewPgMar().setGutter(BigInteger.valueOf(0));
    }

    // ══════════════════════════════════════════════════════════════════════
    // 7. IMAGES
    // ══════════════════════════════════════════════════════════════════════

    public static void addImage(XWPFDocument doc, InputStream imageStream,
                                int pictureType, int widthPx, int heightPx,
                                String description) throws IOException, org.apache.poi.openxml4j.exceptions.InvalidFormatException {
        XWPFParagraph para = doc.createParagraph();
        para.setAlignment(ParagraphAlignment.CENTER);
        XWPFRun run = para.createRun();
        run.addPicture(imageStream, pictureType, description,
                Units.toEMU(widthPx), Units.toEMU(heightPx));
    }
}
