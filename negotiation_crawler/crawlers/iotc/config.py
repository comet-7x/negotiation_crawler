"""IOTC crawler configuration — network constants and document type registry."""

from __future__ import annotations

BASE_URL = "https://iotc.org"

REQUEST_DELAY = 1.5
TIMEOUT = 30.0
HEADERS = {
    "User-Agent": "iotc-research-harvester/1.0 (academic; contact: research@example.com)"
}

DOCUMENTS_PATH = "/documents"
YEAR_PARAM = "field_meeting_year_tid"
LANG_PARAM = "langcode"
DOCTYPE_PARAM = "term_node_tid_depth_i18n"

DOCUMENT_TYPES: dict[str, tuple[str, str]] = {
    "49":   ("Meeting Report",                              "会议报告"),
    "88":   ("Circulars",                                   "通函"),
    "333":  ("CMM Proposals",                               "养护管理措施提案"),
    "877":  ("CNCP applications",                           "合作非缔约方申请"),
    "1916": ("Compliance questionnaires",                   "合规问卷"),
    "402":  ("Compliance Reports",                          "合规报告"),
    "1489": ("Consultant reports",                          "咨询报告"),
    "46":   ("Datasets",                                    "数据集"),
    "345":  ("Executive Summaries",                         "执行摘要"),
    "1482": ("FAO Documents",                               "粮农组织文件"),
    "3573": ("Final compliance reports",                    "最终合规报告"),
    "47":   ("General",                                     "通用文件"),
    "90":   ("Guidelines",                                  "指南"),
    "401":  ("Implementation reports",                      "执行报告"),
    "86":   ("Meeting documents",                           "会议文件"),
    "89":   ("Inspection reports",                          "检查报告"),
    "1478": ("Letters of Credentials (available upon request)", "授权书（申请获取）"),
    "1503": ("Letters of Credentials (Observers)",          "授权书（观察员）"),
    "335":  ("Information papers",                          "信息文件"),
    "340":  ("Meeting information",                         "会议信息"),
    "1481": ("Meeting Minutes",                             "会议纪要"),
    "346":  ("National Reports",                            "国家报告"),
    "336":  ("NGO Statements",                              "非政府组织声明"),
    "698":  ("Project report",                              "项目报告"),
    "3572": ("Provisionnal compliance reports",             "临时合规报告"),
    "48":   ("Publications",                                "出版物"),
    "1271": ("Reference Documents",                         "参考文件"),
    "884":  ("Reports from other meetings",                 "其他会议报告"),
    "1917": ("Response to feedback letter",                 "反馈信回复"),
    "1432": ("Stock Assessment Input and Output files",     "种群评估文件"),
    "3571": ("Summary compliance reports",                  "合规摘要报告"),
}

CATEGORY_GROUP: dict[str, str] = {
    "Meeting Report":                              "会议报告类",
    "Meeting documents":                           "会议文件类",
    "Meeting information":                         "会议文件类",
    "Meeting Minutes":                             "会议文件类",
    "Executive Summaries":                         "会议文件类",
    "Circulars":                                   "通函类",
    "CMM Proposals":                               "提案类",
    "Implementation reports":                      "提案类",
    "Compliance Reports":                          "合规报告类",
    "Final compliance reports":                    "合规报告类",
    "Provisionnal compliance reports":             "合规报告类",
    "Summary compliance reports":                  "合规报告类",
    "Compliance questionnaires":                   "合规报告类",
    "Response to feedback letter":                 "合规报告类",
    "National Reports":                            "国家报告类",
    "Information papers":                          "信息文件类",
    "NGO Statements":                              "信息文件类",
    "Reports from other meetings":                 "参考报告类",
    "Consultant reports":                          "参考报告类",
    "Project report":                              "参考报告类",
    "FAO Documents":                               "参考报告类",
    "Datasets":                                    "科学数据类",
    "Stock Assessment Input and Output files":     "科学数据类",
    "Reference Documents":                         "参考文件类",
    "Publications":                                "出版物类",
    "Guidelines":                                  "指南类",
    "General":                                     "通用文件类",
    "CNCP applications":                           "行政文件类",
    "Inspection reports":                          "行政文件类",
    "Letters of Credentials (available upon request)": "行政文件类",
    "Letters of Credentials (Observers)":          "行政文件类",
}

VIEWS = [
    {
        "doc_type": name,
        "doc_type_zh": zh,
        "category_group": CATEGORY_GROUP.get(name, "其他"),
        "tid": tid,
    }
    for tid, (name, zh) in DOCUMENT_TYPES.items()
]
