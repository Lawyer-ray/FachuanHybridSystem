"""OnlyOffice 编辑器配置签发。

DS（Document Server）开启 JWT 后，前端挂载编辑器时的 config **整体**要签名：
`config.token = HS256(config, JWT_SECRET)`。签名必须由后端做——浏览器里放密钥
等于把密钥发给所有人。

参考：https://api.onlyoffice.com/docs/docs-api/additional-api/signature/browser/
（token 放在 config 根，覆盖全部字段；HS256 与 DS 容器共享 JWT_SECRET）
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import jwt

from ..config import OnlyOfficeConfig, build_file_url

logger = logging.getLogger(__name__)

# 法穿 AI 改写插件（幕后桥）的 GUID。
#
# 插件本体放在 DS 容器的 `sdkjs-plugins/fachuan-rewrite/`（见
# `deploy/onlyoffice/compose.yaml` 的 volumes），由 DS 自己托管并自动发现；
# 所以这里**只给 guid 做 autostart**，不需要 pluginsData（那是让 DS 去远程拉
# config.json 的路子，跨源、要额外托管，容器内本地文件更干净）。
#
# 配套的两条红线（原型真机验证过，改回去就是「点了没反应且不报错」）：
# 1. `callCommand` 第二参必须 false；2. `Asc.scope` 只能传字符串。
# 详见 `deploy/onlyoffice/plugins/fachuan-rewrite/plugin.js` 顶部注释。
FACHUAN_REWRITE_PLUGIN_GUID = "asc.{A67B4C8F-1F2A-4B6E-9C3D-5E8F7A2B1D04}"

# 插件目录名（与 deploy/onlyoffice/plugins/ 下的子目录、容器内
# sdkjs-plugins/ 下的目录名必须一致）。改目录就要同时改这里和 compose 挂载。
FACHUAN_REWRITE_PLUGIN_DIR = "fachuan-rewrite"

# 预处理阶段：纯只读（改是复审工作台的事）。官方语义：edit/review/comment
# 均为 false 时即使 mode=edit 也只进查看器，没有修订与批注入口。
PERMISSIONS_VIEW: dict[str, bool] = {
    "edit": False,
    "review": False,
    "comment": False,
    "download": True,
    "print": True,
    "copy": True,
    "chat": False,
}

# 复审阶段：锁定修订（可留痕，不能直接改正文）
PERMISSIONS_REVIEW: dict[str, bool] = {
    "edit": False,
    "review": True,
    "comment": True,
    "download": True,
    "print": True,
    "copy": True,
    "chat": False,
}

# 完全编辑：律师直接改
PERMISSIONS_EDIT: dict[str, bool] = {
    "edit": True,
    "review": True,
    "comment": True,
    "download": True,
    "print": True,
    "copy": True,
    "chat": False,
}

# copy 显式放开：律师需要复制条款；chat 显式关闭：DS 内置协作聊天对单律师场景
# 无意义，且文本会经过 DS——法律保密场景不留给灰色地带。

_MODE_TO_PERMISSIONS = {
    "view": PERMISSIONS_VIEW,
    "review": PERMISSIONS_REVIEW,
    "edit": PERMISSIONS_EDIT,
}

# 后缀 → documentType（官方支持清单的常用子集）。未命中返回空串：
# 伪装成 word 会让 word 编辑器去打开 xlsm/wps 之类的文件，表现为空白画布。
_DOC_TYPE = {
    "docx": "word",
    "doc": "word",
    "docm": "word",
    "dotx": "word",
    "odt": "word",
    "rtf": "word",
    "txt": "word",
    "epub": "word",
    "fb2": "word",
    "htm": "word",
    "html": "word",
    "md": "word",
    "wps": "word",
    "xlsx": "cell",
    "xls": "cell",
    "xlsb": "cell",
    "xlsm": "cell",
    "ods": "cell",
    "csv": "cell",
    "pptx": "slide",
    "ppt": "slide",
    "potx": "slide",
    "pps": "slide",
    "odp": "slide",
    "pdf": "pdf",
}


def document_type_of(file_name: str) -> str:
    """未知/无后缀返回空串，调用方应提示「该格式暂不支持在线预览」。"""
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return _DOC_TYPE.get(ext, "")


def file_type_of(file_name: str) -> str:
    """提取小写后缀；无后缀返回空串（不伪造 docx）。"""
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def make_document_key(source_path: str, version: str = "", saved_version: int = 0) -> str:
    """DS 按 key 缓存文档：内容变了 key 必须变，否则看到旧内容。

    key 标识的是**文档版本**：同一文件同一版本必须稳定——否则 DS 缓存
    永不复用（每次重开都重新下载转换），且两个用户同开同一文档会被 DS
    当成两份独立文档，协作修订互相不可见。因此哈希原料只用「原始路径 +
    version + saved_version」，**签名参数绝不能参与**（sig 含时间戳，混进
    去就是每次签发 key 必变）。saved_version 在保存回写（DS status=2/6）
    落盘后递增：律师编辑保存即换 key，下次打开 DS 重新取新内容。
    """
    raw = f"{source_path}|{version}|{saved_version}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def build_editor_config(
    cfg: OnlyOfficeConfig,
    *,
    file_url_path: str,
    file_name: str,
    document_key: str,
    mode: str = "review",
    user_id: str = "",
    user_name: str = "",
    lang: str = "zh-CN",
    plugins: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组出可直接交给 DocsAPI.DocEditor 的 config（含 token）。

    file_url_path 是带 sig 签名参数的代理路径（进 document.url）；
    document_key 由调用方用 make_document_key 对**原始路径**计算后传入——
    签名参数含时间戳，绝不能混进 key（见 make_document_key 的说明）。
    """
    perms = _MODE_TO_PERMISSIONS.get(mode, PERMISSIONS_REVIEW)
    doc_type = document_type_of(file_name)

    editor_config: dict[str, Any] = {
        # 一律用 edit 打开：view 模式下 DS 不创建可交互画布（实测无 iframe、无报错）。
        # 官方语义：permissions.edit=false 时即使 mode=edit 也进查看器；
        # review:true + mode=edit 才是「仅审阅模式」。「只读 / 锁定修订 /
        # 完全编辑」由 permissions 字典逐项声明。
        "mode": "edit",
        "lang": lang,
        "user": {"id": user_id, "name": user_name},
        "callbackUrl": build_file_url(cfg.internal_url, "/api/v1/onlyoffice/callback"),
        "customization": {
            "compactHeader": True,
            "hideRightMenu": True,
            "autosave": True,
            # 不开 forcesave，保存回调只在「最后一个用户关闭文档」时触发（status=2）；
            # 律师把工作台一直挂着就永远没有保存回调，修订落不了盘。
            "forcesave": True,
            "uiTheme": "theme-classic-light",
            # 已存在的修订痕迹（w:ins / w:del）**是否显示**由 reviewDisplay 决定，
            # 不是由 trackChanges 决定——这是两件不同的事：
            #   trackChanges  = 我现在敲字要不要留痕（录制）
            #   reviewDisplay = 文档里**已有**的痕迹要不要画出来（回放）
            # DS 默认 `reviewDisplay: 'original'`（见 api.js 注释），即按「修订前的
            # 原文」渲染，画布上**看不到任何删除线/下划线/批注框**。症状极具迷惑性：
            # WPS/Word 打开同一份 docx 满是修订，OnlyOffice 画布干干净净，看着像
            # 「AI 没改成」——真机 A/B 实测（同一 docx，只改 reviewDisplay）：默认形态
            # 审阅面板不出现，改 markup 后「审查更改」面板立刻出现。
            # 因此**所有模式**都必须显式给 markup：律师打开就是要看改了什么，
            # 藏起来等于预览失真。view 模式也适用——只读不等于可以隐瞒修订。
            # showReviewChanges 让「审阅」工具的修订视图开关处于展开态（与 markup 配套）。
            "review": {
                "reviewDisplay": "markup",
                "showReviewChanges": True,
            },
        },
    }
    if mode == "review":
        # trackChanges 覆盖 permissions.review：强制当前用户处于修订模式，
        # 是比纯 permissions 更强的「锁定修订」（官方 customization.review）。
        # 注意保留上面已设的 reviewDisplay / showReviewChanges，只补 trackChanges。
        review = dict(editor_config["customization"]["review"])
        review["trackChanges"] = True
        editor_config["customization"]["review"] = review
    if plugins:
        editor_config["plugins"] = plugins

    # 划词直改的核心入口：插件必须在文档就绪前 autostart，否则宿主页
    # 收不到 `ready` 握手，选区 / 改写全链路都不通。
    #
    # **autostart 与 pluginsData 必须成对**：只给 autostart 时 DS 不知道去哪
    # 取 config.json，插件不会加载，且**无任何报错**（症状：右键菜单里没有
    # 我们的入口，只有 DS 自带的 AI✨）。原型就是两者都给的。
    #
    # 只在可编辑/可审阅的模式挂：view（纯只读）下插件无从落笔，
    # 挂上去只会让律师看到一个用不了的入口。
    if mode in ("review", "edit") and doc_type == "word":
        merged = dict(editor_config.get("plugins") or {})
        autostart = list(merged.get("autostart") or [])
        if FACHUAN_REWRITE_PLUGIN_GUID not in autostart:
            autostart.append(FACHUAN_REWRITE_PLUGIN_GUID)
        merged["autostart"] = autostart

        # config 由 DS 自己托管（compose 把插件目录挂进 sdkjs-plugins），
        # 所以地址用 DS 的公网可达前缀拼。浏览器能访问 docserver_url，
        # DS 自己服务自己托管的静态文件也不需要回连宿主。
        merged["pluginsData"] = [
            f"{cfg.docserver_url.rstrip('/')}/sdkjs-plugins/{FACHUAN_REWRITE_PLUGIN_DIR}/config.json"
        ]
        editor_config["plugins"] = merged

    config: dict[str, Any] = {
        "documentType": doc_type,
        "document": {
            "fileType": file_type_of(file_name),
            "key": document_key,
            # 官方限制 title 最长 128 字符，超出行为未定义
            "title": file_name[:128],
            "url": build_file_url(cfg.internal_url, file_url_path),
            "permissions": perms,
        },
        "editorConfig": editor_config,
        "type": "desktop",
        "width": "100%",
        "height": "100%",
    }

    config["token"] = jwt.encode(config, cfg.jwt_secret, algorithm="HS256")
    return config


def decode_callback_token(cfg: OnlyOfficeConfig, token: str) -> dict[str, Any] | None:
    """校验并解出 DS 回调里的 body（DS 把状态回调也签了名）；失败返回 None。

    官方语义：token 里的数据才是可信的请求体；验不过的回调**不能**回落
    信任 raw body（尤其接上保存回写后，伪造 url 就是 SSRF/任意覆盖）。
    """
    try:
        return jwt.decode(token, cfg.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        logger.warning("OnlyOffice 回调 token 校验失败")
        return None


# ───────── DS 取文件用的签名（可重复使用） ─────────
# 为什么不用项目既有的 download_tickets：那张票据是**一次性**的，而 DS 会重试
# （首拉超时、重连、多阶段转换各取一次），第一次消费掉之后全部 401。
# 这里签一个「URL + 用户 + 有效期」的 HMAC，只要没过期就能反复取同一个文件。


def sign_file_token(secret: str, src: str, user_id: str, ttl_seconds: int = 14400) -> str:
    """为 src（站内路径）签一个可重复使用的访问令牌。

    TTL 4 小时：DS 在缓存逐出、重启、forcesave 重组等场景都可能重拉源文件，
    过短的超时会让长时间挂着的编辑器突然取不到文件。
    """
    exp = int(time.time()) + ttl_seconds
    raw = f"{src}|{user_id}|{exp}"
    sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{exp}.{sig}"


def verify_file_token(secret: str, src: str, token: str) -> str | None:
    """校验签名令牌，返回 user_id；失败返回 None。"""
    try:
        uid, exp_s, sig = token.split(".", 2)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return None
    if exp < int(time.time()):
        return None
    raw = f"{src}|{uid}|{exp}"
    expect = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expect, sig):
        return None
    return uid
