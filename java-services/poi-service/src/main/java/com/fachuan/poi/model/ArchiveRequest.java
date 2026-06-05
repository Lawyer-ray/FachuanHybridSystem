package com.fachuan.poi.model;

import java.util.List;
import lombok.Data;

/**
 * Archive document generation request.
 * Contains all data needed for 案卷封面, 结案归档登记表, 卷内目录.
 */
@Data
public class ArchiveRequest {

    // Basic case info
    private String caseName;
    private String caseType; // "刑事" / "民事" / "行政"
    private String caseNumber; // e.g. "(2006)粤0604刑初155号"
    private String causeOfAction; // 案由
    private String courtName; // 管辖法院
    private String caseStage; // 案件阶段
    private String trialResult; // 审理结果
    private String oaCaseNumber; // OA编号

    // Party info
    private String ourPartyName; // 我方当事人
    private String opposingPartyName; // 对方当事人
    private String leadLawyer; // 主办律师

    // Dates
    private String startDate;
    private String archiveDate;
    private String year;

    // Contract info
    private String contractName;
    private String contractType;

    // Archive materials
    private List<ArchiveItem> archiveItems;

    // Catalog entries
    private List<CatalogEntry> catalogEntries;

    // ── Inner classes ──

    @Data
    public static class ArchiveItem {
        private String name;
        private String pages;
        private String note;

        public ArchiveItem() {}
        public ArchiveItem(String name, String pages, String note) {
            this.name = name;
            this.pages = pages;
            this.note = note;
        }
    }

    @Data
    public static class CatalogEntry {
        private String sequenceNumber;
        private String materialName;
        private String pageNumbers;

        public CatalogEntry() {}
        public CatalogEntry(String seq, String name, String pages) {
            this.sequenceNumber = seq;
            this.materialName = name;
            this.pageNumbers = pages;
        }
    }
}
