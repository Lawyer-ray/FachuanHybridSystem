package com.fachuan.poi.service;

import com.fachuan.poi.model.ComplaintRequest;
import com.fachuan.poi.util.DocxHelper;
import org.apache.poi.xwpf.usermodel.*;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * 起诉状 (Complaint) document generation using Apache POI.
 * Showcases: merged tables, styled paragraphs, section breaks, content controls.
 */
@Service
public class ComplaintService {

    public byte[] generate(ComplaintRequest req) throws IOException {
        XWPFDocument doc = new XWPFDocument();

        // ── Page setup ──
        DocxHelper.setA4Defaults(doc);

        // ── Title ──
        XWPFParagraph titlePara = doc.createParagraph();
        titlePara.setAlignment(ParagraphAlignment.CENTER);
        titlePara.setSpacingAfter(400);
        XWPFRun titleRun = titlePara.createRun();
        titleRun.setText("民  事  起  诉  状");
        titleRun.setBold(true);
        titleRun.setFontSize(22);
        titleRun.setFontFamily("微软雅黑");

        // ── Court info ──
        XWPFParagraph courtPara = doc.createParagraph();
        courtPara.setAlignment(ParagraphAlignment.CENTER);
        courtPara.setSpacingAfter(200);
        XWPFRun courtRun = courtPara.createRun();
        courtRun.setText(req.getCourtName());
        courtRun.setFontSize(14);
        courtRun.setFontFamily("仿宋");

        // ── Parties table (merged cells for form layout) ──
        String[][] partiesData = {
            {"原告", req.getPlaintiffName(), "身份证号/统一社会信用代码", req.getPlaintiffIdNumber()},
            {"", "住所地", "", req.getPlaintiffAddress()},
            {"", "联系电话", "", req.getPlaintiffPhone()},
            {"法定代表人", req.getPlaintiffLegalRepresentative() != null ? req.getPlaintiffLegalRepresentative() : "/", "", ""},
            {"被告", req.getDefendantName(), "身份证号/统一社会信用代码", req.getDefendantIdNumber()},
            {"", "住所地", "", req.getDefendantAddress()},
            {"", "联系电话", "", req.getDefendantPhone()},
        };
        DocxHelper.createMergedTable(doc, partiesData, new int[]{2000, 3000, 3000, 4000});

        // Add spacing
        doc.createParagraph().setSpacingAfter(200);

        // ── 诉讼请求 (Litigation Claims) ──
        addSectionTitle(doc, "诉讼请求");
        if (req.getLitigationClaims() != null) {
            for (int i = 0; i < req.getLitigationClaims().size(); i++) {
                DocxHelper.addNumberedItem(doc, req.getLitigationClaims().get(i), i + 1);
            }
        }

        doc.createParagraph().setSpacingAfter(100);

        // ── 事实与理由 (Facts and Reasons) ──
        addSectionTitle(doc, "事实与理由");
        if (req.getFactsAndReasons() != null) {
            String[] paragraphs = req.getFactsAndReasons().split("\n");
            for (String p : paragraphs) {
                if (!p.trim().isEmpty()) {
                    XWPFParagraph bodyPara = doc.createParagraph();
                    bodyPara.setFirstLineIndent(480); // 2-char indent
                    bodyPara.setSpacingAfter(120);
                    bodyPara.setAlignment(ParagraphAlignment.BOTH);
                    XWPFRun run = bodyPara.createRun();
                    run.setText(p.trim());
                    run.setFontFamily("仿宋");
                    run.setFontSize(14);
                }
            }
        }

        doc.createParagraph().setSpacingAfter(100);

        // ── 证据清单 (Evidence List) ──
        if (req.getEvidenceList() != null && !req.getEvidenceList().isEmpty()) {
            addSectionTitle(doc, "证据清单");
            XWPFParagraph evPara = doc.createParagraph();
            evPara.setFirstLineIndent(480);
            XWPFRun evRun = evPara.createRun();
            evRun.setText(req.getEvidenceList());
            evRun.setFontFamily("仿宋");
            evRun.setFontSize(14);
            doc.createParagraph().setSpacingAfter(100);
        }

        // ── Footer: 此致 + 落款 ──
        XWPFParagraph thisTo = doc.createParagraph();
        thisTo.setSpacingBefore(400);
        XWPFRun thisToRun = thisTo.createRun();
        thisToRun.setText("此致");
        thisToRun.setFontFamily("仿宋");
        thisToRun.setFontSize(14);

        XWPFParagraph courtSign = doc.createParagraph();
        courtSign.setFirstLineIndent(480);
        XWPFRun courtSignRun = courtSign.createRun();
        courtSignRun.setText(req.getCourtName());
        courtSignRun.setFontFamily("仿宋");
        courtSignRun.setFontSize(14);

        // Signature block
        doc.createParagraph().setSpacingAfter(600);

        // Right-aligned signature
        XWPFParagraph sigDate = doc.createParagraph();
        sigDate.setAlignment(ParagraphAlignment.RIGHT);
        sigDate.setSpacingAfter(200);
        XWPFRun dateRun = sigDate.createRun();
        dateRun.setText(req.getSignatureDate() != null ? req.getSignatureDate() : "    年    月    日");
        dateRun.setFontFamily("仿宋");
        dateRun.setFontSize(14);

        // Signature with tab-aligned layout
        String[][] sigData = {
            {"起诉人（签名）：", req.getPlaintiffName()},
            {"委托诉讼代理人：", req.getLawyerName() != null ? req.getLawyerName() : "/"},
            {"律  师  事  务  所：", req.getLawyerFirm() != null ? req.getLawyerFirm() : "/"},
            {"执  业  证  号：", req.getLawyerLicense() != null ? req.getLawyerLicense() : "/"},
        };
        DocxHelper.createMergedTable(doc, sigData, new int[]{3500, 5500});

        // ── Save ──
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        doc.write(baos);
        doc.close();
        return baos.toByteArray();
    }

    private void addSectionTitle(XWPFDocument doc, String title) {
        XWPFParagraph para = doc.createParagraph();
        para.setSpacingBefore(200);
        para.setSpacingAfter(120);
        XWPFRun run = para.createRun();
        run.setText(title + "：");
        run.setBold(true);
        run.setFontFamily("黑体");
        run.setFontSize(14);
    }
}
