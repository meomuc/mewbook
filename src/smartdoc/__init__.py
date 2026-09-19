"""MewBook ("Mèo Mực") -- metadata-first ebook/document manager.

`__version__` is the single source of truth for the product version: the
package metadata (pyproject.toml, via hatch's dynamic version), the About
dialog, the log header, the Windows exe's version resource
(packaging/MewBook.spec) and the installer (packaging/MewBook.iss) all read
it from here. Versioning follows Semantic Versioning 2.0.0 -- see
"Versioning & releases" in README.md.
"""

__version__ = "1.0.0"

APP_NAME = "MewBook"
APP_DISPLAY_NAME = "Mèo Mực"
APP_DESCRIPTION = "Trình quản lý tài liệu/ebook theo metadata"
APP_PUBLISHER = "Anhtiensinh"
APP_COPYRIGHT = "© 2026 Anhtiensinh. Bảo lưu mọi quyền."
