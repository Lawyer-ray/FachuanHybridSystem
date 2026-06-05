package com.fachuan.poi.model;

import java.util.List;
import java.util.Map;
import lombok.Data;

/**
 * 尽调报告 generation request — structured data for due diligence report.
 * Showcases complex POI features: charts, nested tables, multi-section layout.
 */
@Data
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

    // ── Inner classes ──

    @Data
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
    }

    @Data
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
    }

    @Data
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
    }

    @Data
    public static class ReportSection {
        private String title;
        private int level; // 1=heading1, 2=heading2, 3=heading3
        private String content;
        private List<Map<String, String>> tableData; // optional table in section
        private List<String> bulletPoints; // optional bullet list

        public ReportSection() {}
    }
}
