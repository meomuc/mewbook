"""MewBook ("Mèo Mực") -- metadata-first ebook/document manager.

`__version__` is the single source of truth for the product version: the
package metadata (pyproject.toml, via hatch's dynamic version), the About
dialog, the log header, the Windows exe's version resource
(packaging/MewBook.spec) and the installer (packaging/MewBook.iss) all read
it from here. Versioning follows Semantic Versioning 2.0.0 -- see
"Versioning & releases" in README.md.
"""

__version__ = "1.0.0"

# Names and publisher: the single place the UI, log header, exe metadata and HTTP User-Agent read them from
# (a partner's co-branding, decision D9, is deferred; the logo/icon files are resolved in presentation/resources.py).
APP_NAME = "MewBook"
APP_DISPLAY_NAME = "Mèo Mực"
APP_DESCRIPTION = "Trình quản lý tài liệu/ebook theo metadata"
APP_PUBLISHER = "Anhtiensinh"
APP_COPYRIGHT = "© 2026 Anhtiensinh. Phần mềm tự do theo giấy phép AGPL-3.0-or-later."
# Licence shown in Help -> About and in the installer (see LICENSE, docs/legal/SPDX_POLICY.md).
APP_LICENSE_ID = "AGPL-3.0-or-later"
APP_LICENSE_URL = "https://www.gnu.org/licenses/agpl-3.0.html"
# Where the exact source of *this* version lives, with "{version}" filled from __version__
# (e.g. "https://<host>/<owner>/<repo>/tree/v{version}"). Empty until the public repository
# exists: About then shows a text fallback instead of a link. Set before the first release.
APP_SOURCE_URL_TEMPLATE = ""
# A GitHub-style "latest release" JSON (tag_name, html_url) for the optional, off-by-default update check
# (application/update_checker.py). Empty until the public repository exists; set it together with the URL above.
# Example: "https://api.github.com/repos/<owner>/<repo>/releases/latest"
APP_UPDATE_FEED_URL = ""
