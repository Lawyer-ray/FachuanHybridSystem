package com.fachuan.poi.model;

import java.util.List;
import java.util.Map;

/**
 * 尽调报告 generation request — structured data for due diligence report.
 * Showcases complex POI features: charts, nested tables, multi-section layout.
 */
public class ReportRequest {

    // Report metadata
    private String reportTitle;
    private String projectName;
    private String reportDate;
    private String author;
    private String confidentialityLevel; // "机密" / "保密" / "内部"

    // Target company info
    private String companyName;
    private String companyRegistrationNumber;
    private String registeredCapital;
    private String establishedDate;
    private String legalRepresentative;
    private String businessScope;

    // Financial data (for chart generation)
    private List<FinancialYear> financialData;

    // Equity structure (for nested table)
    private List<EquityHolder> equityStructure;

    // Risk items
    private List<RiskItem> riskItems;

    // Section content (free-form HTML or structured sections)
    private List<ReportSection> sections;

    // Getters/setters
    public String getReportTitle() { return reportTitle; }
    public void setReportTitle(String reportTitle) { this.reportTitle = reportTitle; }
    public String getProjectName() { return projectName; }
    public void setProjectName(String projectName) { this.projectName = projectName; }
    public String getReportDate() { return reportDate; }
    public void setReportDate(String reportDate) { this.reportDate = reportDate; }
    public String getAuthor() { return author; }
    public void setAuthor(String author) { this.author = author; }
    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String v) { this.confidentialityLevel = v; }
    public String getCompanyName() { return companyName; }
    public void setCompanyName(String companyName) { this.companyName = companyName; }
    public String getCompanyRegistrationNumber() { return companyRegistrationNumber; }
    public void setCompanyRegistrationNumber(String v) { this.companyRegistrationNumber = v; }
    public String getRegisteredCapital() { return registeredCapital; }
    public void setRegisteredCapital(String registeredCapital) { this.registeredCapital = registeredCapital; }
    public String getEstablishedDate() { return establishedDate; }
    public void setEstablishedDate(String establishedDate) { this.establishedDate = establishedDate; }
    public String getLegalRepresentative() { return legalRepresentative; }
    public void setLegalRepresentative(String v) { this.legalRepresentative = v; }
    public String getBusinessScope() { return businessScope; }
    public void setBusinessScope(String businessScope) { this.businessScope = businessScope; }
    public List<FinancialYear> getFinancialData() { return financialData; }
    public void setFinancialData(List<FinancialYear> financialData) { this.financialData = financialData; }
    public List<EquityHolder> getEquityStructure() { return equityStructure; }
    public void setEquityStructure(List<EquityHolder> equityStructure) { this.equityStructure = equityStructure; }
    public List<RiskItem> getRiskItems() { return riskItems; }
    public void setRiskItems(List<RiskItem> riskItems) { this.riskItems = riskItems; }
    public List<ReportSection> getSections() { return sections; }
    public void setSections(List<ReportSection> sections) { this.sections = sections; }

    // ── Inner classes ──

    public static class FinancialYear {
        private int year;
        private double revenue;
        private double profit;
        private double totalAssets;
        private double totalLiabilities;

        public FinancialYear() {}
        public FinancialYear(int year, double revenue, double profit, double totalAssets, double totalLiabilities) {
            this.year = year;
            this.revenue = revenue;
            this.profit = profit;
            this.totalAssets = totalAssets;
            this.totalLiabilities = totalLiabilities;
        }

        public int getYear() { return year; }
        public void setYear(int year) { this.year = year; }
        public double getRevenue() { return revenue; }
        public void setRevenue(double revenue) { this.revenue = revenue; }
        public double getProfit() { return profit; }
        public void setProfit(double profit) { this.profit = profit; }
        public double getTotalAssets() { return totalAssets; }
        public void setTotalAssets(double totalAssets) { this.totalAssets = totalAssets; }
        public double getTotalLiabilities() { return totalLiabilities; }
        public void setTotalLiabilities(double totalLiabilities) { this.totalLiabilities = totalLiabilities; }
    }

    public static class EquityHolder {
        private String name;
        private double percentage;
        private String type; // "自然人" / "法人"
        private String contributionMethod; // "货币" / "实物" / "知识产权"

        public EquityHolder() {}
        public EquityHolder(String name, double percentage, String type, String contributionMethod) {
            this.name = name;
            this.percentage = percentage;
            this.type = type;
            this.contributionMethod = contributionMethod;
        }

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public double getPercentage() { return percentage; }
        public void setPercentage(double percentage) { this.percentage = percentage; }
        public String getType() { return type; }
        public void setType(String type) { this.type = type; }
        public String getContributionMethod() { return contributionMethod; }
        public void setContributionMethod(String v) { this.contributionMethod = v; }
    }

    public static class RiskItem {
        private String category; // "法律风险" / "财务风险" / "合规风险" / "经营风险"
        private String description;
        private String severity; // "高" / "中" / "低"
        private String recommendation;

        public RiskItem() {}
        public RiskItem(String category, String description, String severity, String recommendation) {
            this.category = category;
            this.description = description;
            this.severity = severity;
            this.recommendation = recommendation;
        }

        public String getCategory() { return category; }
        public void setCategory(String category) { this.category = category; }
        public String getDescription() { return description; }
        public void setDescription(String description) { this.description = description; }
        public String getSeverity() { return severity; }
        public void setSeverity(String severity) { this.severity = severity; }
        public String getRecommendation() { return recommendation; }
        public void setRecommendation(String recommendation) { this.recommendation = recommendation; }
    }

    public static class ReportSection {
        private String title;
        private int level; // 1=heading1, 2=heading2, 3=heading3
        private String content;
        private List<Map<String, String>> tableData; // optional table in section
        private List<String> bulletPoints; // optional bullet list

        public ReportSection() {}

        public String getTitle() { return title; }
        public void setTitle(String title) { this.title = title; }
        public int getLevel() { return level; }
        public void setLevel(int level) { this.level = level; }
        public String getContent() { return content; }
        public void setContent(String content) { this.content = content; }
        public List<Map<String, String>> getTableData() { return tableData; }
        public void setTableData(List<Map<String, String>> tableData) { this.tableData = tableData; }
        public List<String> getBulletPoints() { return bulletPoints; }
        public void setBulletPoints(List<String> bulletPoints) { this.bulletPoints = bulletPoints; }
    }
}
