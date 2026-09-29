"""macOS 系统剪贴板文件写入服务（NSPasteboard）。

为什么需要它：浏览器对「往系统剪贴板写文件」限制极严——W3C 剪贴板规范只保证
text/plain、text/html、image/png 三种类型，Chrome 系写不进 application/pdf
（web 自定义格式只有 Chromium 应用能读）。而本系统后端与律师工作在同一台
Mac 上，由后端直写 NSPasteboard 的 public.file-url，效果与在 Finder 里 ⌘C
复制文件完全一致：任意浏览器里点「复制」，微信等应用 ⌘V 即可粘出文件本体。

pyobjc 实现注意（均已实测）：
- URL 必须放进 NSMutableArray（addObject_ 会 retain）；直接把 Python list 内联
  传给 writeObjects_ 会静默失败——返回 True 但剪贴板是空的；
- 旧式 declareTypes/setData 每个类型只保留最后一份，多文件必须走 writeObjects。
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.core.clipboard")


class MacClipboardFileService:
    """把文件以 file-url 形式写入 macOS 系统剪贴板（同 Finder 复制）。"""

    def is_available(self) -> bool:  # pragma: no cover
        if platform.system() != "Darwin":
            return False
        try:
            import AppKit
            import Foundation

            del AppKit, Foundation
        except ImportError:
            return False
        return True

    def copy_file_paths(self, paths: list[Path]) -> int:  # pragma: no cover
        """写入一组文件路径，返回成功落板的数量；不可用环境返回 0。"""
        if not self.is_available():
            return 0

        import Foundation
        from AppKit import NSPasteboard

        existing = [p for p in paths if p.is_file()]
        if not existing:
            return 0

        NSURL: Any = Foundation.NSURL
        urls: Any = Foundation.NSMutableArray.arrayWithCapacity_(len(existing))
        for p in existing:
            urls.addObject_(NSURL.fileURLWithPath_(str(p)))

        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if not pasteboard.writeObjects_(urls):
            logger.warning("NSPasteboard.writeObjects 失败: %s 个文件", len(existing))
            return 0
        return len(existing)
