"""完整的默认数据配置 - 包含文件模板、文件夹模板和绑定关系"""

from __future__ import annotations

from typing import Any


def get_complete_default_data() -> dict[str, Any]:
    """
    获取完整的默认数据配置

    Returns:
        包含文件模板、文件夹模板和绑定关系的字典
    """
    return {
        "folder_templates": [
            {
                "name": "合同文件夹",
                "template_type": "contract",
                "case_types": [],
                "case_stages": [],
                "contract_types": ["all"],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "structure": {
                    "children": [
                        {
                            "id": "folder_1767248233072_s9rssw63q",
                            "name": "1-律师资料",
                            "children": [
                                {"id": "folder_1767248282647_e4290qqcu", "name": "1-合同", "children": []},
                                {"id": "folder_1767248291398_z3eo83nhg", "name": "2-补充协议", "children": []},
                                {"id": "folder_1767248296585_1sr2d2dxa", "name": "3-发票", "children": []},
                                {"id": "folder_1767253153361_onc3r034w", "name": "4-其他资料", "children": []},
                            ],
                        },
                        {"id": "folder_1767248312320_4vivqk7yv", "name": "2-客户资料", "children": []},
                    ]
                },
                "is_default": True,
                "is_active": True,
            },
            {
                "name": "民事一审起诉",
                "template_type": "case",
                "case_types": ["civil"],
                "case_stages": ["first_trial"],
                "contract_types": [],
                "legal_statuses": ["plaintiff"],
                "legal_status_match_mode": "any",
                "structure": {
                    "children": [
                        {
                            "id": "folder_1767233774579_ljsxh6im4",
                            "name": "一审",
                            "children": [
                                {
                                    "id": "folder_1767233814952_7hatlncsj",
                                    "name": "1-立案材料",
                                    "children": [
                                        {
                                            "id": "folder_1767234083753_3tn5gbwkr",
                                            "name": "1-起诉状和反诉答辩状",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767234093146_etqnssxu5",
                                            "name": "2-当事人身份证明",
                                            "children": [],
                                        },
                                        {"id": "folder_1767234105784_45wytn65d", "name": "3-委托材料", "children": []},
                                        {"id": "folder_1767234130228_ntijfdj3a", "name": "4-证据目录", "children": []},
                                        {"id": "folder_1767234139086_lfaf1tf7b", "name": "5-证据材料", "children": []},
                                        {
                                            "id": "folder_1767234153997_gsdc2w6bm",
                                            "name": "6-送达地址确认书",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767234166134_ap83tlcct",
                                            "name": "7-退费账户确认书",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767234707146_8q1ifw47t",
                                            "name": "8-保全申请书及保函",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767234727828_x3hrbie59",
                                            "name": "9-其他立案材料",
                                            "children": [],
                                        },
                                    ],
                                },
                                {
                                    "id": "folder_1767233835345_efzv1utkj",
                                    "name": "2-庭审准备",
                                    "children": [
                                        {"id": "folder_1767234891108_pyy4exuwd", "name": "1-问题清单", "children": []},
                                        {"id": "folder_1767234518262_elq8uyz42", "name": "2-庭审提纲", "children": []},
                                        {"id": "folder_1767234524908_iis0tq9uq", "name": "3-质证意见", "children": []},
                                        {
                                            "id": "folder_1767234538118_mnzy80by9",
                                            "name": "4-时间轴大事记",
                                            "children": [],
                                        },
                                        {"id": "folder_1767234600551_e0qk8nqn1", "name": "5-代理意见", "children": []},
                                        {"id": "folder_1767236546614_ed6nk20dm", "name": "6-其他材料", "children": []},
                                    ],
                                },
                                {
                                    "id": "folder_1767235143559_vaoblr4vv",
                                    "name": "3-结案文书",
                                    "children": [
                                        {
                                            "id": "folder_1767235178392_9gto7zcyu",
                                            "name": "1-撤诉申请书",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767235187390_v79wdfkh8",
                                            "name": "2-解除查封申请书",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767235227090_0yontho86",
                                            "name": "3-和解(调解)协议",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767235720367_ij59gezdq",
                                            "name": "4-申请退费(待申请)",
                                            "children": [],
                                        },
                                    ],
                                },
                                {"id": "folder_1767235760272_vga4rbfld", "name": "4-邮件往来", "children": []},
                            ],
                        }
                    ]
                },
                "is_default": True,
                "is_active": True,
            },
            {
                "name": "民事一审答辩",
                "template_type": "case",
                "case_types": ["civil"],
                "case_stages": ["first_trial"],
                "contract_types": [],
                "legal_statuses": ["defendant"],
                "legal_status_match_mode": "any",
                "structure": {
                    "children": [
                        {
                            "id": "folder_1767240664617_jonttgx5",
                            "name": "一审",
                            "children": [
                                {
                                    "id": "folder_1767240745584_tdw42vw1g",
                                    "name": "1-答辩材料",
                                    "children": [
                                        {
                                            "id": "folder_1767240769278_0krhuz3yz",
                                            "name": "1-答辩状(反诉状)",
                                            "children": [],
                                        },
                                        {"id": "folder_1767240808378_pq2gqjckd", "name": "2-证据目录", "children": []},
                                        {"id": "folder_1767240820092_dg7vs5hu6", "name": "3-证据材料", "children": []},
                                        {
                                            "id": "folder_1767240849185_qvqifo6kk",
                                            "name": "4-当事人身份证明",
                                            "children": [],
                                        },
                                        {"id": "folder_1767240877211_s0204ub4b", "name": "5-委托材料", "children": []},
                                        {
                                            "id": "folder_1767240916751_587ozn5gn",
                                            "name": "6-其他答辩材料",
                                            "children": [],
                                        },
                                    ],
                                },
                                {
                                    "id": "folder_1767240664620_qul256kc",
                                    "name": "2-庭审准备",
                                    "children": [
                                        {"id": "folder_1767240664620_fxxtqw07", "name": "1-问题清单", "children": []},
                                        {"id": "folder_1767240664620_hwz7zkcx", "name": "2-庭审提纲", "children": []},
                                        {"id": "folder_1767240664620_tjsup8ib", "name": "3-质证意见", "children": []},
                                        {
                                            "id": "folder_1767240664620_vlgiac3z",
                                            "name": "4-时间轴大事记",
                                            "children": [],
                                        },
                                        {"id": "folder_1767240664621_zhldh3ak", "name": "5-代理意见", "children": []},
                                        {"id": "folder_1767240664621_48w1vely", "name": "6-其他材料", "children": []},
                                    ],
                                },
                                {
                                    "id": "folder_1767240664621_mkoie73p",
                                    "name": "4-结案文书",
                                    "children": [
                                        {
                                            "id": "folder_1767240664622_c040f0we",
                                            "name": "1-和解(调解)协议",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1767240664622_ckctj4n3",
                                            "name": "2-其他结案文书",
                                            "children": [],
                                        },
                                    ],
                                },
                                {"id": "folder_1767240664622_rtqxrxy4", "name": "5-邮件往来", "children": []},
                            ],
                        }
                    ]
                },
                "is_default": True,
                "is_active": True,
            },
            {
                "name": "申请执行文件夹",
                "template_type": "case",
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "contract_types": [],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "structure": {
                    "children": [
                        {
                            "id": "folder_1774250377874_3xc8kz0e",
                            "name": "执行",
                            "children": [
                                {
                                    "id": "folder_1774250377874_wgkg21aw",
                                    "name": "1-立案材料",
                                    "children": [
                                        {
                                            "id": "folder_1774250377875_km2h1b4f",
                                            "name": "1-强制执行申请书",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1774250377876_a93zfd2s",
                                            "name": "2-当事人身份证明",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1774250377876_aepfz20q",
                                            "name": "3-委托材料",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1774250377877_07bdwj6d",
                                            "name": "4-限制性措施",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1774250377878_bd72h67r",
                                            "name": "5-执行依据及生效证明",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1774250377878_991ago5r",
                                            "name": "6-送达地址确认书",
                                            "children": [],
                                        },
                                        {
                                            "id": "folder_1774250377879_1tztdlni",
                                            "name": "7-退费账户确认书",
                                            "children": [],
                                        },
                                    ],
                                },
                                {
                                    "id": "folder_1774250377885_1r5w975h",
                                    "name": "2-邮件往来",
                                    "children": [],
                                },
                            ],
                        }
                    ]
                },
                "is_default": True,
                "is_active": True,
            },
        ],
        "document_templates": [
            {
                "name": "补充协议",
                "template_type": "contract",
                "contract_sub_type": "supplementary_agreement",
                "case_sub_type": None,
                "file_path": "1-合同模板/补充协议.docx",
                "contract_types": ["all"],
                "case_types": [],
                "case_stages": [],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "所函",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "power_of_attorney_materials",
                "file_path": "2-案件材料/4-通用材料/1-授权委托材料/所函.docx",
                "contract_types": [],
                "case_types": ["all"],
                "case_stages": ["all"],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "授权委托书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "power_of_attorney_materials",
                "file_path": "2-案件材料/4-通用材料/1-授权委托材料/授权委托书.docx",
                "contract_types": [],
                "case_types": ["all"],
                "case_stages": ["all"],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "法定代表人身份证明书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "power_of_attorney_materials",
                "file_path": "2-案件材料/4-通用材料/1-授权委托材料/法定代表人身份证明书.docx",
                "contract_types": [],
                "case_types": ["all"],
                "case_stages": ["all"],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "民商事合同",
                "template_type": "contract",
                "contract_sub_type": "contract",
                "case_sub_type": None,
                "file_path": "1-合同模板/民商事代理合同.docx",
                "contract_types": ["civil"],
                "case_types": [],
                "case_stages": [],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "顾问合同",
                "template_type": "contract",
                "contract_sub_type": "contract",
                "case_sub_type": None,
                "file_path": "1-合同模板/顾问合同.docx",
                "contract_types": ["advisor"],
                "case_types": [],
                "case_stages": [],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "刑事合同",
                "template_type": "contract",
                "contract_sub_type": "contract",
                "case_sub_type": None,
                "file_path": "1-合同模板/刑事代理合同.docx",
                "contract_types": ["criminal"],
                "case_types": [],
                "case_stages": [],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "强制执行申请书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "application_materials",
                "file_path": "2-案件材料/3-申请执行材料/强制执行申请书.docx",
                "contract_types": [],
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "纳入失信被执行人名单的申请书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "application_materials",
                "file_path": "2-案件材料/3-申请执行材料/限制性措施/纳入失信被执行人名单的申请书.docx",
                "contract_types": [],
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "通过媒体公布不履行义务信息的申请书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "application_materials",
                "file_path": "2-案件材料/3-申请执行材料/限制性措施/通过媒体公布不履行义务信息的申请书.docx",
                "contract_types": [],
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "限制被执行人出境申请书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "application_materials",
                "file_path": "2-案件材料/3-申请执行材料/限制性措施/限制被执行人出境申请书.docx",
                "contract_types": [],
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "限制高消费申请书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "application_materials",
                "file_path": "2-案件材料/3-申请执行材料/限制性措施/限制高消费申请书.docx",
                "contract_types": [],
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
            {
                "name": "广州法院电子送达地址确认书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "service_address_materials",
                "file_path": "2-案件材料/4-通用材料/3-送达地址确认书/广州电子送达地址确认书.docx",
                "contract_types": [],
                "case_types": ["all"],
                "case_stages": ["all"],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "applicable_institutions": ["广州", "广州市"],
                "is_active": True,
            },
            {
                "name": "广州对方当事人送达地址及相关信息确认书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "service_address_materials",
                "file_path": "2-案件材料/4-通用材料/3-送达地址确认书/广州对方当事人送达地址及相关信息确认书.docx",
                "contract_types": [],
                "case_types": ["all"],
                "case_stages": ["all"],
                "legal_statuses": [],
                "legal_status_match_mode": "any",
                "applicable_institutions": ["广州", "广州市"],
                "is_active": True,
            },
            {
                "name": "番禺法院领退转款账户确认书",
                "template_type": "case",
                "contract_sub_type": None,
                "case_sub_type": "refund_account_materials",
                "file_path": "2-案件材料/4-通用材料/5-退费账户确认书/番禺法院领退转款账户确认书.docx",
                "contract_types": [],
                "case_types": ["civil", "execution"],
                "case_stages": ["enforcement"],
                "legal_statuses": ["applicant"],
                "legal_status_match_mode": "any",
                "is_active": True,
            },
        ],
        "bindings": [
            {
                "document_template_name": "补充协议",
                "folder_template_name": "合同文件夹",
                "folder_node_id": "folder_1767248291398_z3eo83nhg",
            },
            {
                "document_template_name": "民商事合同",
                "folder_template_name": "合同文件夹",
                "folder_node_id": "folder_1767248282647_e4290qqcu",
            },
            {
                "document_template_name": "顾问合同",
                "folder_template_name": "合同文件夹",
                "folder_node_id": "folder_1767248282647_e4290qqcu",
            },
            {
                "document_template_name": "刑事合同",
                "folder_template_name": "合同文件夹",
                "folder_node_id": "folder_1767248282647_e4290qqcu",
            },
            {
                "document_template_name": "法定代表人身份证明书",
                "folder_template_name": "民事一审起诉",
                "folder_node_id": "folder_1767234093146_etqnssxu5",
            },
            {
                "document_template_name": "法定代表人身份证明书",
                "folder_template_name": "民事一审答辩",
                "folder_node_id": "folder_1767240849185_qvqifo6kk",
            },
            {
                "document_template_name": "授权委托书",
                "folder_template_name": "民事一审起诉",
                "folder_node_id": "folder_1767234105784_45wytn65d",
            },
            {
                "document_template_name": "授权委托书",
                "folder_template_name": "民事一审答辩",
                "folder_node_id": "folder_1767240877211_s0204ub4b",
            },
            {
                "document_template_name": "所函",
                "folder_template_name": "民事一审答辩",
                "folder_node_id": "folder_1767240877211_s0204ub4b",
            },
            {
                "document_template_name": "所函",
                "folder_template_name": "民事一审起诉",
                "folder_node_id": "folder_1767234105784_45wytn65d",
            },
            {
                "document_template_name": "广州法院电子送达地址确认书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377878_991ago5r",
            },
            {
                "document_template_name": "广州对方当事人送达地址及相关信息确认书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377878_991ago5r",
            },
            {
                "document_template_name": "番禺法院领退转款账户确认书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377879_1tztdlni",
            },
            {
                "document_template_name": "强制执行申请书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377875_km2h1b4f",
            },
            {
                "document_template_name": "纳入失信被执行人名单的申请书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377877_07bdwj6d",
            },
            {
                "document_template_name": "限制被执行人出境申请书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377877_07bdwj6d",
            },
            {
                "document_template_name": "通过媒体公布不履行义务信息的申请书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377877_07bdwj6d",
            },
            {
                "document_template_name": "限制高消费申请书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377877_07bdwj6d",
            },
            {
                "document_template_name": "所函",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377876_aepfz20q",
            },
            {
                "document_template_name": "授权委托书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377876_aepfz20q",
            },
            {
                "document_template_name": "法定代表人身份证明书",
                "folder_template_name": "申请执行文件夹",
                "folder_node_id": "folder_1774250377876_a93zfd2s",
            },
        ],
    }
