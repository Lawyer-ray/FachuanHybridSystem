package com.fachuan.poi.model;

import java.util.List;
import java.util.Map;

/**
 * 起诉状 generation request — structured data for complaint document.
 */
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

    // Getters and setters
    public String getCourtName() { return courtName; }
    public void setCourtName(String courtName) { this.courtName = courtName; }
    public String getPlaintiffName() { return plaintiffName; }
    public void setPlaintiffName(String plaintiffName) { this.plaintiffName = plaintiffName; }
    public String getPlaintiffType() { return plaintiffType; }
    public void setPlaintiffType(String plaintiffType) { this.plaintiffType = plaintiffType; }
    public String getPlaintiffIdNumber() { return plaintiffIdNumber; }
    public void setPlaintiffIdNumber(String plaintiffIdNumber) { this.plaintiffIdNumber = plaintiffIdNumber; }
    public String getPlaintiffAddress() { return plaintiffAddress; }
    public void setPlaintiffAddress(String plaintiffAddress) { this.plaintiffAddress = plaintiffAddress; }
    public String getPlaintiffPhone() { return plaintiffPhone; }
    public void setPlaintiffPhone(String plaintiffPhone) { this.plaintiffPhone = plaintiffPhone; }
    public String getPlaintiffLegalRepresentative() { return plaintiffLegalRepresentative; }
    public void setPlaintiffLegalRepresentative(String v) { this.plaintiffLegalRepresentative = v; }
    public String getDefendantName() { return defendantName; }
    public void setDefendantName(String defendantName) { this.defendantName = defendantName; }
    public String getDefendantType() { return defendantType; }
    public void setDefendantType(String defendantType) { this.defendantType = defendantType; }
    public String getDefendantIdNumber() { return defendantIdNumber; }
    public void setDefendantIdNumber(String defendantIdNumber) { this.defendantIdNumber = defendantIdNumber; }
    public String getDefendantAddress() { return defendantAddress; }
    public void setDefendantAddress(String defendantAddress) { this.defendantAddress = defendantAddress; }
    public String getDefendantPhone() { return defendantPhone; }
    public void setDefendantPhone(String defendantPhone) { this.defendantPhone = defendantPhone; }
    public String getLawyerName() { return lawyerName; }
    public void setLawyerName(String lawyerName) { this.lawyerName = lawyerName; }
    public String getLawyerFirm() { return lawyerFirm; }
    public void setLawyerFirm(String lawyerFirm) { this.lawyerFirm = lawyerFirm; }
    public String getLawyerLicense() { return lawyerLicense; }
    public void setLawyerLicense(String lawyerLicense) { this.lawyerLicense = lawyerLicense; }
    public String getCauseOfAction() { return causeOfAction; }
    public void setCauseOfAction(String causeOfAction) { this.causeOfAction = causeOfAction; }
    public String getCaseNumber() { return caseNumber; }
    public void setCaseNumber(String caseNumber) { this.caseNumber = caseNumber; }
    public List<String> getLitigationClaims() { return litigationClaims; }
    public void setLitigationClaims(List<String> litigationClaims) { this.litigationClaims = litigationClaims; }
    public String getFactsAndReasons() { return factsAndReasons; }
    public void setFactsAndReasons(String factsAndReasons) { this.factsAndReasons = factsAndReasons; }
    public String getEvidenceList() { return evidenceList; }
    public void setEvidenceList(String evidenceList) { this.evidenceList = evidenceList; }
    public String getFilingDate() { return filingDate; }
    public void setFilingDate(String filingDate) { this.filingDate = filingDate; }
    public String getSignatureDate() { return signatureDate; }
    public void setSignatureDate(String signatureDate) { this.signatureDate = signatureDate; }
}
