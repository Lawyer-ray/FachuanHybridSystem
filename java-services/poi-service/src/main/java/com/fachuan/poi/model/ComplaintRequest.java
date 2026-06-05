package com.fachuan.poi.model;

import java.util.List;
import java.util.Map;
import lombok.Data;

/**
 * 起诉状 generation request — structured data for complaint document.
 */
@Data
public class ComplaintRequest {

    // Court info
    private String courtName;

    // Plaintiff info
    private String plaintiffName;
    private String plaintiffType; // "自然人" or "法人"
    private String plaintiffIdNumber;
    private String plaintiffAddress;
    private String plaintiffPhone;
    private String plaintiffLegalRepresentative;

    // Defendant info
    private String defendantName;
    private String defendantType;
    private String defendantIdNumber;
    private String defendantAddress;
    private String defendantPhone;

    // Agent info (律师)
    private String lawyerName;
    private String lawyerFirm;
    private String lawyerLicense;

    // Litigation info
    private String causeOfAction; // 案由
    private String caseNumber; // 案号 (optional, for counter-claims)
    private List<String> litigationClaims; // 诉讼请求
    private String factsAndReasons; // 事实与理由
    private String evidenceList; // 证据清单 (optional)

    // Filing info
    private String filingDate;
    private String signatureDate;
}
