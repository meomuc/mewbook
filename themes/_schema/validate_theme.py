#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kiểm tra gói theme MewBook trước khi nhập.

Cách dùng:
    python validate_theme.py <thư mục gói | file .zip | theme.json> [--schema đường/dẫn/theme.schema.json]

Hỗ trợ chuẩn 1.0, 1.1 (token link, khối layouts) 1.2 (ornaments.backdrop) và 1.3 (backdrop leaves, leaf-pile).
Mã thoát: 0 = đạt, 1 = có LỖI (không được nhập), 2 = không đọc được gói.
CẢNH BÁO không chặn việc nhập nhưng phải báo lại cho người dùng.
Không cần thư viện ngoài; nếu có `jsonschema` thì dùng thêm để kiểm tra chặt hơn.
"""
import json, math, os, re, sys, tempfile, zipfile

TOKENS = ["bg","rail","panel","surface","surface2","ink","ink2","ink3","line","line2","accent","accentink",
          "accentsoft","shelf","shelftop","under","shadow","ok","warn","err","scrim"]
OPTIONAL_TOKENS = ["link"]   # 1.1
RGBA_KEYS = {"under", "shadow", "scrim"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA = re.compile(r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0|1|0?\.\d+)\s*\)$")
ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# ---------- màu ----------
def rgb(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
def lum(h):
    r, g, b = rgb(h); return 0.2126*_lin(r) + 0.7152*_lin(g) + 0.0722*_lin(b)
def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + .05) / (lb + .05)
def lab(h):
    def f(t): return t ** (1/3) if t > 0.008856 else 7.787*t + 16/116
    r, g, b = (_lin(c) for c in rgb(h))
    x = (r*.4124 + g*.3576 + b*.1805) / .95047
    y = (r*.2126 + g*.7152 + b*.0722)
    z = (r*.0193 + g*.1192 + b*.9505) / 1.08883
    return 116*f(y) - 16, 500*(f(x) - f(y)), 200*(f(y) - f(z))
def delta_e(a, b):
    return math.dist(lab(a), lab(b))

# ---------- quy tắc ----------
CONTRAST_TEXT = 4.5      # chữ thường
CONTRAST_UI = 3.0        # viền điều khiển, accent trên nền, chữ lớn/đậm
DELTA_E_MIN = 20         # ok / warn / err / accent phải khác nhau rõ
BACKDROP_MAX = 1.35      # hình phong cảnh phải thật mờ so với nền
BACKDROPS = {"none", "karst", "terraces", "hills-flowers", "pines", "dunes", "aurora", "leaves", "leaf-pile"}
def blend(base, top, a):
    b, t_ = rgb(base), rgb(top)
    return "#" + "".join(f"{round(b[i]*(1-a) + t_[i]*a):02X}" for i in range(3))

def check(theme, root, content_bg="bg"):
    E, W = [], []
    need = ["schema_version", "id", "name", "dark", "description", "tokens", "fonts"]
    for k in need:
        if k not in theme: E.append(f"Thiếu trường bắt buộc: {k}")
    if E: return E, W
    lays = theme.get("layouts", {})
    if not isinstance(lays, dict): E.append("layouts phải là object")
    for lid, lv in (lays.items() if isinstance(lays, dict) else []):
        for k in (lv.get("tokens") or {}):
            if k not in TOKENS + OPTIONAL_TOKENS: E.append(f"layouts.{lid}.tokens có token lạ: {k}")
    if not str(theme["schema_version"]).startswith("1."):
        E.append(f"schema_version {theme['schema_version']} không được hỗ trợ (cần 1.x)")
    if not ID.match(theme["id"]): E.append(f"id '{theme['id']}' phải là chữ thường không dấu, nối bằng gạch ngang")
    if len(theme["description"]) > 90: E.append("description dài quá 90 ký tự")

    t = theme["tokens"]
    for k in TOKENS:
        if k not in t: E.append(f"Thiếu token: {k}"); continue
        pat = RGBA if k in RGBA_KEYS else HEX
        if not pat.match(str(t[k])): E.append(f"Token {k} = '{t[k]}' sai định dạng ({'rgba(...)' if k in RGBA_KEYS else '#RRGGBB'})")
    extra = set(t) - set(TOKENS) - set(OPTIONAL_TOKENS)
    if "link" in t and not HEX.match(str(t["link"])): E.append(f"Token link = '{t['link']}' sai định dạng (#RRGGBB)")
    if extra: E.append(f"Token lạ (không có trong chuẩn): {', '.join(sorted(extra))}")
    if E: return E, W

    # sáng/tối khớp với nền
    is_dark_bg = lum(t["bg"]) < 0.18
    if is_dark_bg != bool(theme["dark"]):
        E.append(f"dark = {theme['dark']} nhưng nền bg {t['bg']} là nền {'tối' if is_dark_bg else 'sáng'}")

    # tương phản chữ
    for fg in ("ink", "ink2"):
        for bgk in ("bg", "rail", "panel", "surface", "surface2"):
            c = contrast(t[fg], t[bgk])
            if c < CONTRAST_TEXT: E.append(f"Tương phản {fg} trên {bgk} = {c:.2f}:1 (cần ≥ {CONTRAST_TEXT})")
    for bgk in ("bg", "rail", "panel", "surface"):
        c = contrast(t["ink3"], t[bgk])
        if c < CONTRAST_UI: W.append(f"ink3 trên {bgk} = {c:.2f}:1 (nên ≥ {CONTRAST_UI}; chỉ dùng cho chữ phụ không bắt buộc)")
    c = contrast(t["accentink"], t["accent"])
    if c < CONTRAST_TEXT: E.append(f"Chữ accentink trên nền accent = {c:.2f}:1 (cần ≥ {CONTRAST_TEXT})")
    lk = "link" if "link" in t else "accent"
    for bgk in ("panel", "surface"):
        c = contrast(t[lk], t[bgk])
        if c < CONTRAST_TEXT: E.append(f"{lk} (chữ liên kết) trên {bgk} = {c:.2f}:1 (cần ≥ {CONTRAST_TEXT})")
    c = contrast(t["accent"], t[content_bg])
    if c < CONTRAST_UI: E.append(f"accent trên nền nội dung {content_bg} = {c:.2f}:1 (cần ≥ {CONTRAST_UI} cho viền chọn bìa, nút chính)")
    for k in ("ok", "warn", "err"):
        for bgk in ("panel", "surface", "rail"):
            c = contrast(t[k], t[bgk])
            if c < CONTRAST_UI: E.append(f"Màu {k} trên {bgk} = {c:.2f}:1 (cần ≥ {CONTRAST_UI})")
    c = contrast(t["line2"], t["surface"])
    if c < 1.5: W.append(f"Viền line2 trên surface quá mờ ({c:.2f}:1)")
    c = contrast(t["accentsoft"], t["panel"])
    if c > 2.0: W.append(f"accentsoft khá đậm so với panel ({c:.2f}:1) — chữ ink đặt trên nó có thể khó đọc")
    c = contrast(t["ink"], t["accentsoft"])
    if c < CONTRAST_TEXT: E.append(f"Chữ ink trên accentsoft (mục đang chọn) = {c:.2f}:1 (cần ≥ {CONTRAST_TEXT})")

    # màu trạng thái khác nhau rõ
    ks = ["ok", "warn", "err", "accent"]
    for i in range(len(ks)):
        for j in range(i+1, len(ks)):
            d = delta_e(t[ks[i]], t[ks[j]])
            if d < DELTA_E_MIN: E.append(f"{ks[i]} và {ks[j]} quá giống nhau (ΔE = {d:.1f}, cần ≥ {DELTA_E_MIN})")

    # kệ nổi trên nền
    c = max(contrast(t["shelf"], t[content_bg]), contrast(t["shelftop"], t[content_bg]))
    if c < 1.25: W.append(f"Vạch kệ gần như lẫn vào nền (tương phản {c:.2f}:1)")

    # phông
    for role in ("ui", "content", "display"):
        f = theme["fonts"].get(role)
        if not f or "family" not in f: E.append(f"Thiếu phông '{role}'"); continue
        files = f.get("files", [])
        for p in files:
            if not os.path.isfile(os.path.join(root, p)): E.append(f"Phông {role}: không thấy file {p} trong gói")
        if files:
            lic = f.get("license")
            if not lic or not os.path.isfile(os.path.join(root, lic)):
                E.append(f"Phông {role}: kèm file phông nhưng thiếu file giấy phép")
            else:
                txt = open(os.path.join(root, lic), encoding="utf-8", errors="ignore").read()
                if "Open Font License" not in txt and "Apache License" not in txt:
                    E.append(f"Phông {role}: giấy phép không phải OFL/Apache 2.0")
        if f.get("vietnamese") is not True: W.append(f"Phông {role} chưa xác nhận có đủ dấu tiếng Việt")

    # trang trí
    o = theme.get("ornaments", {})
    fr = o.get("frame", {})
    if fr.get("style") == "wood":
        for k in ("light", "dark", "ink"):
            if k not in fr: E.append(f"ornaments.frame kiểu wood thiếu '{k}'")
        if "ink" in fr and "light" in fr and contrast(fr["ink"], fr["light"]) < CONTRAST_TEXT:
            E.append(f"Chữ trên khung gỗ = {contrast(fr['ink'], fr['light']):.2f}:1 (cần ≥ {CONTRAST_TEXT})")
    nt = o.get("notice", {})
    if nt.get("style") == "chalkboard":
        for k in ("bg", "ink", "frame"):
            if k not in nt: E.append(f"ornaments.notice kiểu chalkboard thiếu '{k}'")
        if "bg" in nt and "ink" in nt and contrast(nt["ink"], nt["bg"]) < CONTRAST_TEXT:
            E.append(f"Chữ trên bảng thông báo = {contrast(nt['ink'], nt['bg']):.2f}:1 (cần ≥ {CONTRAST_TEXT})")
    bd = o.get("backdrop", {})
    if bd and bd.get("style", "none") != "none":
        if bd["style"] not in BACKDROPS: E.append(f"backdrop.style '{bd['style']}' không có trong chuẩn")
        op = bd.get("opacity")
        if not isinstance(op, (int, float)) or not (0.02 <= op <= 0.6): E.append("backdrop.opacity phải từ 0.02 đến 0.6")
        else:
            base = t[content_bg]
            for key in ("color", "color2"):
                if key not in bd: continue
                if not HEX.match(bd[key]): E.append(f"backdrop.{key} sai định dạng"); continue
                mix = blend(base, bd[key], op * (1 if key == "color" else .55))
                c = contrast(mix, base)
                if c > BACKDROP_MAX: E.append(f"Hình phong cảnh ({key}) quá đậm: tương phản với nền {c:.2f}:1 (tối đa {BACKDROP_MAX})")
                if c < 1.02 and key == "color": W.append(f"Hình phong cảnh gần như không nhìn thấy ({c:.2f}:1)")
                for fg in ("ink", "ink2"):
                    cc = contrast(t[fg], mix)
                    if cc < CONTRAST_TEXT: E.append(f"Chữ {fg} đặt trên hình phong cảnh = {cc:.2f}:1 (cần ≥ {CONTRAST_TEXT})")
    for p in theme.get("preview", []):
        if not os.path.isfile(os.path.join(root, p)): W.append(f"Thiếu ảnh xem trước {p}")
    return E, W

def load(path):
    if os.path.isfile(path) and path.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="mewtheme_")
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in n.split("/"): raise ValueError(f"Đường dẫn không an toàn trong zip: {n}")
            z.extractall(tmp)
        cands = [os.path.join(d, "theme.json") for d, _, fs in os.walk(tmp) if "theme.json" in fs]
        if len(cands) != 1: raise ValueError("Gói phải có đúng một theme.json")
        return json.load(open(cands[0], encoding="utf-8")), os.path.dirname(cands[0])
    if os.path.isdir(path):
        return json.load(open(os.path.join(path, "theme.json"), encoding="utf-8")), path
    return json.load(open(path, encoding="utf-8")), os.path.dirname(os.path.abspath(path))

def main(argv):
    if not argv: print(__doc__); return 2
    schema_path = None
    if "--schema" in argv:
        i = argv.index("--schema"); schema_path = argv[i+1]; argv = argv[:i] + argv[i+2:]
    try:
        theme, root = load(argv[0])
    except Exception as ex:
        print(f"KHÔNG ĐỌC ĐƯỢC GÓI: {ex}"); return 2
    E, W = check(theme, root)
    sp = schema_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.schema.json")
    try:
        import jsonschema
        if os.path.isfile(sp):
            v = jsonschema.Draft202012Validator(json.load(open(sp, encoding="utf-8")))
            for er in v.iter_errors(theme):
                E.append("Schema: " + "/".join(map(str, er.path)) + f" — {er.message}")
    except ImportError:
        W.append("Chưa cài jsonschema — chỉ chạy bộ kiểm tra tích hợp")
    name = f"{theme.get('name','?')} ({theme.get('id','?')})"
    print(f"Theme: {name}")
    for w in W: print("  CẢNH BÁO:", w)
    for e in E: print("  LỖI:", e)
    print("KẾT QUẢ:", "ĐẠT" if not E else f"KHÔNG ĐẠT — {len(E)} lỗi")
    return 0 if not E else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
