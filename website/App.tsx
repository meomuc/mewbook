// SPDX-License-Identifier: AGPL-3.0-or-later
import React, { useState, useEffect } from "react";
import {
  Database, Search, Image as ImageIcon, Sparkles,
  ShieldCheck, Heart, Download, Facebook, Coffee,
  Cloud, Sun, CloudRain, Moon, BookOpen,
  CheckCircle2, Clock, Wrench, AlertCircle
} from "lucide-react";
import content from "./content.json";
import { detectWeather, themeFromClock, type WeatherKey } from "./weather";

const logoUrl = "/assets/logo.png";

const weatherConfig: Record<WeatherKey, {
  label: string;
  short: string;
  icon: React.ElementType;
  bg: string;
  bgPage: string;
  cardBg: string;
  text: string;
  textMuted: string;
  accent: string;
  windowBg: string;
  description: string;
}> = {
  nang: {
    label: "Nắng",
    short: "Nắng",
    icon: Sun,
    bg: "#FFF8F0",
    bgPage: "bg-[#FFF8F0]",
    cardBg: "bg-white",
    text: "text-[#5A3E36]",
    textMuted: "text-[#8B6B5E]",
    accent: "#FF8C42",
    windowBg: "from-[#87CEEB] via-[#FFE9A8] to-[#FFD27F]",
    description: "Nắng vàng rọi qua cửa sổ. Mèo đang lim dim."
  },
  mua: {
    label: "Mưa",
    short: "Mưa",
    icon: CloudRain,
    bg: "#E8EEF2",
    bgPage: "bg-[#E8EEF2]",
    cardBg: "bg-[#F7FBFF]",
    text: "text-[#2E3E4E]",
    textMuted: "text-[#6B7F92]",
    accent: "#6B8CAE",
    windowBg: "from-[#A8B8C8] via-[#C8D4DF] to-[#9AAFC1]",
    description: "Mưa lộp độp. Trong nhà ấm và thơm mùi sách."
  },
  may: {
    label: "Nhiều mây",
    short: "Mây",
    icon: Cloud,
    bg: "#F5E6CC",
    bgPage: "bg-[#F5E6CC]",
    cardBg: "bg-[#FFF8F0]",
    text: "text-[#5A3E36]",
    textMuted: "text-[#9A7E6E]",
    accent: "#D48A5C",
    windowBg: "from-[#E8DDD0] via-[#F0E6D8] to-[#DDD0BD]",
    description: "Trời âm u dịu nhẹ. Hợp để đọc chậm."
  },
  dem: {
    label: "Đêm",
    short: "Đêm",
    icon: Moon,
    bg: "#2B211E",
    bgPage: "bg-[#2B211E]",
    cardBg: "bg-[#3A2E2A]",
    text: "text-[#F5E6CC]",
    textMuted: "text-[#C4A997]",
    accent: "#FF8C42",
    windowBg: "from-[#1A2636] via-[#2A3A4E] to-[#3D2A1A]",
    description: "Đèn vàng bật. Mèo cuộn tròn bên kệ sách."
  },
};

// versions / roadmap / bugs are generated into content.json by scripts/update-content.js; edit them there.
type Version = { ver: string; date: string; tag: string; tagColor: string; bullets: string[]; download?: { win?: string; size?: string } };
type RoadmapItem = { title: string; desc: string; eta: string; status: string };
type Announcement = { date: string; title: string; text: string };
type Shot = { src: string; title: string; caption: string; w: number; h: number };
type Bug = { id: string; desc: string; status: string; priority: string; color: string };

const meta = content.meta;
const versions = content.versions as Version[];
const roadmap = content.roadmap as RoadmapItem[];
const nextRelease = roadmap.filter(r => r.status === "next"); // "Đang phát triển": the next release, plans that may change
const laterPlans = roadmap.filter(r => r.status !== "next");
// Hand-written notices, newest first (content.json -> announcements; the updater leaves them alone).
const announcements = ((content as { announcements?: Announcement[] }).announcements ?? []);
const bugs = content.bugs as Bug[];
const gallery = (content as { gallery?: Shot[] }).gallery ?? [];
const donate = content.donate as { momo?: string; bank?: string; buymeacoffee?: string; qr?: string };
const latest: Version | undefined = versions[0];
const latestSize = latest?.download?.size;

/** 2026-09-19 -> 19.09.2026 */
const formatDate = (iso: string) => iso.split("-").reverse().join(".");

export default function App() {
  // The weather starts from the visitor's real weather (see weather.ts); picking one by hand switches auto off.
  const [weather, setWeather] = useState<WeatherKey>(themeFromClock);
  const [auto, setAuto] = useState(true);
  const [qrMissing, setQrMissing] = useState(false);
  const [shot, setShot] = useState<number | null>(null); // gallery lightbox: index of the open picture
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const cfg = weatherConfig[weather];
  const isDark = weather === "dem";
  const autoRef = React.useRef(auto);
  autoRef.current = auto;

  useEffect(() => {
    document.documentElement.style.scrollBehavior = "smooth";
  }, []);

  useEffect(() => {
    let cancelled = false;
    detectWeather().then(key => { if (key && !cancelled) setWeather(prev => (autoRef.current ? key : prev)); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (shot === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShot(null);
      else if (e.key === "ArrowRight") setShot(i => (i === null ? i : (i + 1) % gallery.length));
      else if (e.key === "ArrowLeft") setShot(i => (i === null ? i : (i - 1 + gallery.length) % gallery.length));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shot]);

  const pick = (k: WeatherKey) => { setAuto(false); setWeather(k); };

  return (
    <div className={`min-h-screen w-full font-[Quicksand,ui-sans-serif] transition-colors duration-700 ${cfg.bgPage} ${cfg.text} selection:bg-[#FF8C42]/30`}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&family=Quicksand:wght@500;600;700&display=swap');
        * { font-family: "Be Vietnam Pro", sans-serif; }
        h1,h2,h3,.display { font-family: "Quicksand", sans-serif; }
        @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
        @keyframes rain { 0%{transform:translateY(-20px); opacity:0} 20%{opacity:1} 100%{transform:translateY(120px); opacity:0} }
        @keyframes drift { 0%{transform:translateX(-10px)} 100%{transform:translateX(10px)} }
        @keyframes twinkle { 0%,100%{opacity:0.2} 50%{opacity:1} }
        @keyframes sunray { 0%{transform:rotate(0) scale(1); opacity:0.6} 100%{transform:rotate(180deg) scale(1.2); opacity:0.2} }
        @keyframes tail { 0%,100%{transform:rotate(-6deg)} 50%{transform:rotate(8deg)} }
        .paper { background-image: radial-gradient(rgba(0,0,0,0.04) 1px, transparent 1px); background-size: 22px 22px; }
        .paper-dark { background-image: radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px); background-size: 22px 22px; }
      `}</style>

      {/* Header */}
      <header className={`sticky top-0 z-50 backdrop-blur-xl border-b transition-colors duration-700 ${isDark ? "bg-[#2B211E]/80 border-[#4A3A34]" : "bg-[#FFF8F0]/80 border-[#E9DCC6]"}`} style={{ paddingTop: 'var(--safe-area-inset-top, 0px)' }}>
        <div className="mx-auto max-w-[1120px] px-5 md:px-8 h-[96px] flex items-center justify-between">
          <a href="#" className="flex items-center gap-3">
            <div className="w-[83px] h-[83px] rounded-full bg-[#FF8C42] p-1 flex items-center justify-center shadow-[0_4px_12px_rgba(255,140,66,0.3)]">
              <img src={logoUrl} alt="Mèo Mực logo" className="w-full h-full object-contain rounded-full" />
            </div>
            <span className="display font-bold text-[18px] tracking-tight">Mèo Mực <span className="font-medium opacity-70">— MewBook</span></span>
          </a>

          <nav className="hidden md:flex items-center gap-6 text-[14px] font-medium">
            {[
              { id: "tinh-nang", label: "Tính năng" },
              { id: "giao-dien", label: "Giao diện" },
              { id: "phien-ban", label: "Phiên bản" },
              { id: "lo-trinh", label: "Lộ trình" },
              { id: "loi", label: "Lỗi" },
              { id: "donate", label: "Donate" },
            ].map(n => (
              <a key={n.id} href={`#${n.id}`} className={`hover:opacity-100 transition ${isDark ? "opacity-70 hover:text-white" : "opacity-70 hover:text-[#5A3E36]"}`}>{n.label}</a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <div className={`hidden sm:flex items-center p-1 rounded-full ${isDark ? "bg-[#3A2E2A] border border-[#4A3A34]" : "bg-white border border-[#F0E2C8] shadow-sm"}`}>
              {(Object.keys(weatherConfig) as WeatherKey[]).map(k => {
                const w = weatherConfig[k];
                const Icon = w.icon;
                const active = weather === k;
                return (
                  <button
                    key={k}
                    onClick={() => pick(k)}
                    className={`px-3 py-1.5 rounded-full text-[13px] font-semibold flex items-center gap-1.5 transition-all ${active ? "bg-[#FF8C42] text-white shadow" : isDark ? "text-[#C4A997] hover:text-white" : "text-[#8B6B5E] hover:text-[#5A3E36]"}`}
                  >
                    <Icon className="w-4 h-4" /> {w.short}
                  </button>
                );
              })}
            </div>
            <button onClick={() => setIsMenuOpen(!isMenuOpen)} className={`md:hidden w-9 h-9 rounded-full grid place-items-center ${isDark ? "bg-[#3A2E2A] text-[#F5E6CC]" : "bg-white text-[#5A3E36] shadow-sm"}`}>
              <span className="text-[18px]">☰</span>
            </button>
          </div>
        </div>

        {/* mobile weather + nav */}
        <div className={`md:hidden transition-all overflow-hidden ${isMenuOpen ? "max-h-[300px] border-t" : "max-h-0"} ${isDark ? "border-[#4A3A34] bg-[#2B211E]" : "border-[#E9DCC6] bg-[#FFF8F0]"}`}>
          <div className="px-5 py-4 flex flex-col gap-3">
            <div className="flex gap-2 flex-wrap">
              {(Object.keys(weatherConfig) as WeatherKey[]).map(k => {
                const w = weatherConfig[k];
                return (
                  <button key={k} onClick={() => pick(k)} className={`px-3 py-1.5 rounded-full text-[13px] font-semibold border ${weather===k ? "bg-[#FF8C42] text-white border-[#FF8C42]" : isDark ? "border-[#4A3A34] text-[#C4A997]" : "border-[#F0E2C8] bg-white text-[#8B6B5E]"}`}>{w.label}</button>
                );
              })}
            </div>
            <div className="flex gap-4 text-[14px] font-medium pt-2">
              {[
                { id: "tinh-nang", label: "Tính năng" },
              { id: "giao-dien", label: "Giao diện" },
                { id: "phien-ban", label: "Phiên bản" },
                { id: "lo-trinh", label: "Lộ trình" },
                { id: "loi", label: "Lỗi" },
                { id: "donate", label: "Donate" },
              ].map(n => (
                <a key={n.id} href={`#${n.id}`} onClick={()=>setIsMenuOpen(false)} className="opacity-80">{n.label}</a>
              ))}
            </div>
            <p className={`text-[12px] mt-1 ${cfg.textMuted}`}>{cfg.description}</p>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-[1120px] px-5 md:px-8 pt-10 md:pt-16 pb-12 md:pb-20">
        <div className="grid md:grid-cols-[1.15fr_0.85fr] gap-8 md:gap-10 items-start">
          {/* left */}
          <div>
            <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-[12px] font-semibold mb-5 ${isDark ? "bg-[#3A2E2A] text-[#FFC9A3] border border-[#4A3A34]" : "bg-white text-[#5A3E36] border border-[#F0E2C8] shadow-sm"}`}>
              <span className="w-2 h-2 rounded-full bg-[#FF8C42] animate-pulse" />
              {cfg.description}
            </div>
            <h1 className="display text-[40px] md:text-[56px] leading-[0.95] font-bold tracking-tight">
              Đọc sách dễ hơn,<br />
              <span className="relative">sống chill hơn.
                <span className="absolute -bottom-2 left-0 w-full h-[10px] bg-[#FF8C42]/30 -rotate-1 rounded-full" />
              </span>
            </h1>
            <p className={`mt-6 text-[17px] leading-relaxed max-w-[52ch] ${cfg.textMuted}`}>
              Mèo Mực là phần mềm quản lý sách chạy <b className={`${cfg.text} font-semibold`}>100% trên máy bạn</b>, miễn phí vĩnh viễn. Không thu thập dữ liệu, không ồn ào. Chỉ có bạn, kệ sách, và một con mèo mập ngồi sau lưng.
            </p>

            <div className="mt-7 flex flex-wrap gap-3">
              <a
                href={meta.downloadUrl}
                target="_blank"
                rel="noopener"
                className="group inline-flex items-center gap-3 px-5 py-3 rounded-full bg-[#FF8C42] text-white font-semibold text-[14px] shadow-[0_8px_20px_rgba(255,140,66,0.35)] hover:translate-y-[-1px] transition"
              >
                <Download className="w-4 h-4 group-hover:rotate-6 transition" />
                Tải cho Windows <span className="opacity-70 text-[12px]">.exe</span>
              </a>
              <a
                href={meta.fanpageUrl}
                target="_blank"
                rel="noopener"
                className={`group inline-flex items-center gap-3 px-5 py-3 rounded-full font-semibold text-[14px] border hover:translate-y-[-1px] transition ${isDark ? "bg-[#3A2E2A] border-[#4A3A34] text-[#F5E6CC]" : "bg-white border-[#F0E2C8] text-[#5A3E36] shadow-sm"}`}
              >
                <Facebook className="w-4 h-4" />
                Fanpage Facebook
              </a>
            </div>

            <div className="mt-4 flex items-center gap-3 text-[12px]">
              <span className={`px-2.5 py-1 rounded-full font-medium ${isDark ? "bg-[#3A2E2A] text-[#C4A997]" : "bg-[#F5E6CC] text-[#5A3E36]"}`}>{latest?.ver}{latestSize ? ` • ${latestSize}` : ""} • Miễn phí</span>
              <a href={meta.fanpageUrl} target="_blank" rel="noopener" className={`inline-flex items-center gap-1.5 underline decoration-dotted ${cfg.textMuted}`}> <Facebook className="w-3.5 h-3.5" /> facebook.com/meomuc.mewbook</a>
            </div>

            <div className={`mt-8 inline-flex items-center gap-3 px-4 py-2.5 rounded-2xl ${isDark ? "bg-[#3A2E2A] border border-[#4A3A34]" : "bg-white border border-[#F0E2C8] shadow-[0_6px_20px_rgba(90,62,54,0.06)]"}`}>
              <div className="flex -space-x-2">
                {["M","E","W"].map(ch => (
                  <div key={ch} className="w-7 h-7 rounded-full border-2 border-white bg-[#F5E6CC] grid place-items-center text-[10px] font-bold text-[#5A3E36]">{ch}</div>
                ))}
              </div>
              <p className="text-[13px] leading-tight">
                <span className="font-bold">Không tài khoản, không theo dõi, không quảng cáo</span><br />
                <span className={`${cfg.textMuted} text-[12px]`}>Mèo không đếm like. Mèo đếm số sách được đọc xong.</span>
              </p>
            </div>
          </div>

          {/* right illustration - window + desk */}
          <div className={`relative rounded-[28px] p-3 md:p-4 ${isDark ? "bg-[#3A2E2A] border border-[#4A3A34]" : "bg-white border border-[#F0E2C8] shadow-[0_20px_60px_rgba(90,62,54,0.12)]"} transition-colors duration-700`}>
            {/* window */}
            <div className="relative rounded-[20px] overflow-hidden border-[8px] border-[#5A3E36]/90 bg-[#5A3E36]">
              <div className={`relative h-[300px] md:h-[360px] w-full bg-gradient-to-br ${cfg.windowBg} transition-all duration-700`}>
                {/* paper texture overlay */}
                <div className={`absolute inset-0 ${isDark ? "paper-dark" : "paper"} opacity-40`} />

                {/* weather visuals */}
                {weather === "nang" && (
                  <>
                    <div className="absolute left-1/2 top-[22%] -translate-x-1/2 w-[88px] h-[88px] rounded-full bg-[#FFD27F] shadow-[0_0_40px_20px_rgba(255,210,127,0.6)]" />
                    <div className="absolute inset-0" style={{ animation: "sunray 12s linear infinite" }}>
                      <div className="absolute left-1/2 top-1/2 w-[220px] h-[220px] -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-[#FF8C42]/30" />
                      <div className="absolute left-1/2 top-1/2 w-[300px] h-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-[#FF8C42]/20" />
                    </div>
                    <div className="absolute bottom-0 w-full h-[50%] bg-gradient-to-t from-[#FF8C42]/20 to-transparent" />
                  </>
                )}

                {weather === "mua" && (
                  <>
                    <div className="absolute inset-0 overflow-hidden">
                      {Array.from({ length: 28 }).map((_, i) => (
                        <div key={i} className="absolute w-[2px] h-[18px] bg-white/70 rounded-full" style={{
                          left: `${(i * 13) % 100}%`,
                          top: `-20px`,
                          animation: `rain ${0.8 + Math.random()*0.8}s linear infinite`,
                          animationDelay: `${Math.random()*1.2}s`
                        }} />
                      ))}
                    </div>
                    <div className="absolute bottom-3 left-4 right-4 h-[22px] bg-white/40 rounded-full blur-[2px]" />
                  </>
                )}

                {weather === "may" && (
                  <>
                    {[
                      { top: "22%", left: "10%", w: 90 },
                      { top: "36%", left: "38%", w: 120 },
                      { top: "18%", left: "58%", w: 80 },
                    ].map((c, i) => (
                      <div key={i} className="absolute rounded-full bg-white/70 shadow-[0_6px_20px_rgba(0,0,0,0.06)]" style={{
                        top: c.top, left: c.left, width: c.w, height: c.w*0.6,
                        animation: `drift ${4+i}s ease-in-out infinite alternate`
                      }} />
                    ))}
                  </>
                )}

                {weather === "dem" && (
                  <>
                    {Array.from({ length: 24 }).map((_, i) => (
                      <div key={i} className="absolute w-1 h-1 rounded-full bg-white" style={{
                        left: `${Math.random()*100}%`,
                        top: `${Math.random()*60}%`,
                        animation: `twinkle ${1.5 + Math.random()*2}s ease-in-out infinite`,
                        animationDelay: `${Math.random()*2}s`
                      }} />
                    ))}
                    <div className="absolute bottom-0 left-0 right-0 h-[55%] bg-gradient-to-t from-[#FF8C42]/30 via-[#FF8C42]/10 to-transparent" />
                    <div className="absolute right-[12%] bottom-[18%] w-[36px] h-[48px] rounded-t-[10px] bg-[#FFD27F]/80 blur-[1px] shadow-[0_0_30px_10px_rgba(255,210,127,0.5)]" />
                  </>
                )}

                {/* window cross */}
                <div className="absolute inset-0 grid grid-cols-2 grid-rows-2 gap-[6px] p-[6px] pointer-events-none">
                  <div className="bg-white/10 rounded-[6px]" />
                  <div className="bg-white/10 rounded-[6px]" />
                  <div className="bg-white/10 rounded-[6px]" />
                  <div className="bg-white/10 rounded-[6px]" />
                </div>
              </div>

              {/* sill */}
              <div className="h-[14px] bg-[#8B6B5E] w-full" />
            </div>

            {/* desk area */}
            <div className="relative mt-3 rounded-[16px] bg-[#5A3E36] p-3 flex items-end gap-3">
              <div className="flex-1">
                <div className="flex gap-2 mb-2">
                  <div className="w-10 h-[46px] rounded-[6px] bg-[#F5E6CC] border border-[#E9DCC6] shadow-sm grid place-items-center text-[9px] font-bold text-[#5A3E36] rotate-1">SÁCH</div>
                  <div className="w-8 h-[42px] rounded-[5px] bg-[#FFD27F] border shadow-sm rotate-[-2deg]" />
                  <div className="w-12 h-[8px] rounded-full bg-[#3A2E2A] mt-6" />
                </div>
                <div className="h-[6px] w-full rounded-full bg-[#3A2E2A]" />
              </div>

              {/* cat - main mascot */}
              <div className="relative w-[110px] h-[110px] shrink-0">
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[84px] h-[84px] rounded-full bg-[#FF8C42] shadow-[0_10px_20px_rgba(0,0,0,0.25)] grid place-items-center overflow-hidden" style={{ animation: "float 3.5s ease-in-out infinite" }}>
                  <img src={logoUrl} alt="Mèo Mực - chubby orange cat from behind" className="w-[92%] h-[92%] object-contain" />
                </div>
                {/* tail */}
                <div className="absolute bottom-[18px] -right-1 w-[26px] h-[36px] bg-[#FF8C42] rounded-full origin-bottom" style={{ animation: "tail 1.6s ease-in-out infinite" }} />
                {/* shadow */}
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[70px] h-[10px] bg-black/20 rounded-full blur-[2px]" />
              </div>
            </div>

            <div className={`mt-3 flex items-center justify-between text-[11px] px-1 ${cfg.textMuted}`}>
              <span>● cửa sổ của Mèo • {weatherConfig[weather].label}{auto ? " (theo thời tiết của bạn)" : ""}</span>
              <span className="opacity-70">100% local • offline</span>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="tinh-nang" className="mx-auto max-w-[1120px] px-5 md:px-8 pb-16">
        <div className="flex items-end justify-between gap-4 mb-6">
          <h2 className="display text-[28px] md:text-[34px] font-bold leading-tight">Mèo làm được gì? <span className="opacity-60 font-medium text-[18px]">— ít thôi, nhưng gọn.</span></h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { icon: Database, title: "Quản lý local với SQLite", desc: "Toàn bộ sách nằm trong 1 file .db trên máy bạn. Không cloud, không tài khoản. Mất mạng vẫn đọc." },
            { icon: Search, title: "Tìm kiếm siêu nhanh", desc: "Gõ 2 chữ là ra. Tìm theo tên, tác giả, ghi chú, cả đoạn trích bạn đã highlight." },
            { icon: ImageIcon, title: "Tự lấy bìa & metadata", desc: "Dán ISBN hoặc tên sách, Mèo tự đi lấy bìa, tác giả, năm xuất bản. Khỏi gõ tay." },
            { icon: Sparkles, title: "AI tóm tắt & gợi ý", desc: "Dùng Gemini (key của bạn) để tóm tắt, gợi ý sách tiếp theo theo mood hiện tại." },
            { icon: ShieldCheck, title: "Không đụng file gốc", desc: "Mèo chỉ đọc, không di chuyển, không đổi tên file của bạn. Sách của bạn vẫn là của bạn." },
            { icon: Heart, title: "Giao diện chill, hướng nội", desc: "Không thông báo, không pop-up, không gamification ồn ào. Chỉ có kệ sách và sự yên tĩnh." },
          ].map(f => (
            <div key={f.title} className={`group rounded-[20px] p-5 border transition hover:-translate-y-0.5 ${isDark ? "bg-[#3A2E2A] border-[#4A3A34] hover:border-[#5A4A44]" : "bg-white border-[#F0E2C8] shadow-[0_8px_24px_rgba(90,62,54,0.06)] hover:shadow-[0_12px_32px_rgba(90,62,54,0.1)]"}`}>
              <div className="w-10 h-10 rounded-full bg-[#FF8C42]/15 grid place-items-center mb-3">
                <f.icon className="w-5 h-5 text-[#FF8C42]" />
              </div>
              <h3 className="font-bold text-[15px] mb-1.5">{f.title}</h3>
              <p className={`text-[13px] leading-relaxed ${cfg.textMuted}`}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Gallery: pictures live in content.json -> gallery; files in public/assets/gallery */}
      {gallery.length > 0 && (
        <section id="giao-dien" className="mx-auto max-w-[1120px] px-5 md:px-8 pb-16">
          <div className="mb-6">
            <h2 className="display text-[28px] md:text-[34px] font-bold leading-tight">Giao diện của Mèo <span className="opacity-60 font-medium text-[18px]">— chọn theo tâm trạng.</span></h2>
            <p className={`mt-2 text-[14px] ${cfg.textMuted}`}>Mỗi giao diện có màu, phông chữ và cách bày kệ sách riêng. Bấm vào ảnh để xem lớn.</p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
            {gallery.map((g, i) => (
              <button
                key={g.src}
                onClick={() => setShot(i)}
                className={`group text-left rounded-[20px] overflow-hidden border transition hover:-translate-y-0.5 ${isDark ? "bg-[#3A2E2A] border-[#4A3A34]" : "bg-white border-[#F0E2C8] shadow-[0_8px_24px_rgba(90,62,54,0.06)] hover:shadow-[0_12px_32px_rgba(90,62,54,0.1)]"}`}
              >
                <div className="aspect-[16/10] overflow-hidden bg-black/5">
                  <img src={g.src} alt={g.title} loading="lazy" width={g.w} height={g.h} className="w-full h-full object-cover object-top group-hover:scale-[1.03] transition duration-500" />
                </div>
                <div className="p-3">
                  <div className="font-bold text-[13px]">{g.title}</div>
                  <div className={`text-[11px] leading-snug mt-0.5 ${cfg.textMuted}`}>{g.caption}</div>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {shot !== null && gallery[shot] && (
        <div className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm flex flex-col items-center justify-center p-4 md:p-8" onClick={() => setShot(null)} role="dialog" aria-label={gallery[shot].title}>
          <img src={gallery[shot].src} alt={gallery[shot].title} className="max-h-[80vh] max-w-full rounded-[16px] shadow-2xl" onClick={e => e.stopPropagation()} />
          <div className="mt-4 text-center text-white" onClick={e => e.stopPropagation()}>
            <div className="font-bold text-[15px]">{gallery[shot].title}</div>
            <div className="text-[12px] opacity-70">{gallery[shot].caption} • {shot + 1}/{gallery.length}</div>
            <div className="mt-3 flex justify-center gap-3">
              <button onClick={() => setShot((shot - 1 + gallery.length) % gallery.length)} className="px-4 py-1.5 rounded-full bg-white/15 hover:bg-white/25 text-[13px] font-semibold">← Trước</button>
              <button onClick={() => setShot(null)} className="px-4 py-1.5 rounded-full bg-[#FF8C42] text-[13px] font-semibold">Đóng</button>
              <button onClick={() => setShot((shot + 1) % gallery.length)} className="px-4 py-1.5 rounded-full bg-white/15 hover:bg-white/25 text-[13px] font-semibold">Sau →</button>
            </div>
          </div>
        </div>
      )}

      {/* Versions */}
      <section id="phien-ban" className={`border-y ${isDark ? "bg-[#352A27] border-[#4A3A34]" : "bg-[#FFF8F0] border-[#F0E2C8]"} py-14`}>
        <div className="mx-auto max-w-[1120px] px-5 md:px-8">
          <div className="grid md:grid-cols-[1.1fr_0.9fr] gap-10">
            <div>
              <div className="flex items-center gap-3 mb-6">
                <h2 className="display text-[26px] md:text-[30px] font-bold">Phiên bản & cập nhật</h2>
                <span className={`text-[11px] px-2 py-1 rounded-full border ${isDark ? "border-[#4A3A34] text-[#C4A997]" : "border-[#E9DCC6] bg-white text-[#8B6B5E]"}`}>Tự cập nhật theo mỗi bản phát hành</span>
              </div>

              {announcements.length > 0 && (
                <div className="mb-8 space-y-3" id="thong-bao">
                  <div className={`text-[11px] font-semibold uppercase tracking-wider ${cfg.textMuted}`}>Cập nhật và thông báo</div>
                  {announcements.map(a => (
                    <div key={a.date + a.title} className={`rounded-[16px] p-4 border ${isDark ? "bg-[#3A2E2A] border-[#4A3A34]" : "bg-white border-[#F0E2C8] shadow-sm"}`}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-[14px]">{a.title}</span>
                        <span className={`text-[11px] ${cfg.textMuted}`}>{formatDate(a.date)}</span>
                      </div>
                      <p className={`mt-1.5 text-[13px] leading-relaxed ${cfg.textMuted}`}>{a.text}</p>
                    </div>
                  ))}
                </div>
              )}

              <div className="relative pl-8">
                <div className={`absolute left-[11px] top-2 bottom-2 w-[2px] ${isDark ? "bg-[#4A3A34]" : "bg-[#F0E2C8]"}`} />
                {versions.map(v => (
                  <div key={v.ver} className="relative pb-8">
                    <div className="absolute left-[-28px] top-1 w-5 h-5 rounded-full border-2 bg-[#FF8C42] border-white shadow" />
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-[16px]">{v.ver}</span>
                      <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${v.tagColor}`}>{v.tag}</span>
                      <span className={`text-[12px] ${cfg.textMuted}`}>{formatDate(v.date)}</span>
                    </div>
                    <ul className="mt-2 space-y-1">
                      {v.bullets.map(b => (
                        <li key={b} className={`text-[13px] flex gap-2 ${cfg.textMuted}`}><span className="mt-1 w-1 h-1 rounded-full bg-[#FF8C42] shrink-0" />{b}</li>
                      ))}
                    </ul>
                    {v.download?.win && (
                      <a href={v.download.win} target="_blank" rel="noopener" className="mt-2 inline-block text-[12px] font-semibold underline decoration-dotted text-[#FF8C42]">Tải bản này →</a>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div id="lo-trinh" className={`rounded-[20px] p-5 border ${isDark ? "bg-[#3A2E2A] border-[#4A3A34]" : "bg-white border-[#F0E2C8] shadow-sm"}`}>
              <h3 className="font-bold text-[16px] mb-1">Sắp tới Mèo sẽ làm</h3>
              <p className={`text-[12px] mb-4 ${cfg.textMuted}`}>Mèo làm chậm thôi, nhưng chắc. Không hứa nhiều.</p>
              {nextRelease.length > 0 && (
                <div className="mb-5" id="dang-phat-trien">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="font-bold text-[14px]">Đang phát triển — dự kiến bản kế tiếp</span>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${isDark ? "border-[#4A3A34] text-[#C4A997]" : "border-[#E9DCC6] bg-white text-[#8B6B5E]"}`}>kế hoạch, có thể thay đổi</span>
                  </div>
                  <div className="space-y-3">
                    {nextRelease.map(r => (
                      <div key={r.title} className={`rounded-[14px] p-3 flex justify-between gap-3 ${isDark ? "bg-[#2B211E] border border-[#4A3A34]" : "bg-[#FFF8F0] border border-[#F5E6CC]"}`}>
                        <div className="min-w-0">
                          <div className="font-semibold text-[13px]">{r.title}</div>
                          <div className={`text-[12px] ${cfg.textMuted}`}>{r.desc}</div>
                        </div>
                        <span className={`text-[11px] px-2 py-1 rounded-full h-fit shrink-0 ${isDark ? "bg-[#3A2E2A] text-[#C4A997]" : "bg-white text-[#8B6B5E] border border-[#F0E2C8]"}`}>{r.eta}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="space-y-3">
                {laterPlans.map(r => (
                  <div key={r.title} className={`rounded-[14px] p-3 flex justify-between gap-3 ${isDark ? "bg-[#2B211E] border border-[#4A3A34]" : "bg-[#FFF8F0] border border-[#F5E6CC]"}`}>
                    <div>
                      <div className="font-semibold text-[13px]">{r.title}</div>
                      <div className={`text-[12px] ${cfg.textMuted}`}>{r.desc}</div>
                    </div>
                    <span className={`text-[11px] px-2 py-1 rounded-full h-fit shrink-0 ${isDark ? "bg-[#3A2E2A] text-[#C4A997]" : "bg-white text-[#8B6B5E] border border-[#F0E2C8]"}`}>{r.eta}</span>
                  </div>
                ))}
              </div>
              <div className={`mt-4 rounded-[12px] p-3 text-[12px] flex gap-2 ${isDark ? "bg-[#2B211E] text-[#C4A997]" : "bg-[#F5E6CC] text-[#5A3E36]"}`}>
                <BookOpen className="w-4 h-4 shrink-0 mt-0.5" />
                Mèo ưu tiên sự ổn định hơn là nhiều tính năng. Mỗi bản cập nhật đều phải làm Mèo thấy chill hơn, không phải bận hơn.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Bugs */}
      <section id="loi" className="mx-auto max-w-[1120px] px-5 md:px-8 py-14">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <h2 className="display text-[26px] md:text-[30px] font-bold">Lỗi & tình trạng xử lý</h2>
          <span className={`text-[11px] px-2.5 py-1 rounded-full ${isDark ? "bg-[#3A2E2A] text-[#C4A997] border border-[#4A3A34]" : "bg-white border border-[#F0E2C8] text-[#8B6B5E]"}`}>Tự cập nhật theo mỗi bản phát hành</span>
        </div>

        <div className={`rounded-[20px] overflow-hidden border ${isDark ? "bg-[#3A2E2A] border-[#4A3A34]" : "bg-white border-[#F0E2C8] shadow-[0_10px_30px_rgba(90,62,54,0.06)]"}`}>
          <div className={`hidden md:grid grid-cols-[90px_1fr_140px_90px] gap-3 px-5 py-3 text-[11px] font-semibold uppercase tracking-wider border-b ${isDark ? "border-[#4A3A34] text-[#C4A997] bg-[#2B211E]" : "border-[#F0E2C8] text-[#9A7E6E] bg-[#FFF8F0]"}`}>
            <span>ID</span><span>Mô tả</span><span>Trạng thái</span><span>Ưu tiên</span>
          </div>
          {bugs.map(b => (
            <div key={b.id} className={`grid md:grid-cols-[90px_1fr_140px_90px] gap-2 md:gap-3 px-5 py-3.5 text-[13px] border-b last:border-0 ${isDark ? "border-[#4A3A34] hover:bg-[#352A27]" : "border-[#F5E6CC] hover:bg-[#FFF8F0]"} transition`}>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${b.color}`} />
                <span className="font-mono font-semibold">{b.id}</span>
              </div>
              <span className={`${cfg.textMuted} md:text-[13px] leading-snug`}>{b.desc}</span>
              <span className="flex items-center gap-1.5">
                {b.status === "Đã sửa" ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : b.status === "Đang xử lý" ? <Wrench className="w-4 h-4 text-amber-500" /> : <Clock className="w-4 h-4 text-zinc-400" />}
                <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${b.status === "Đã sửa" ? "bg-emerald-500/15 text-emerald-700" : b.status === "Đang xử lý" ? "bg-amber-500/15 text-amber-700" : isDark ? "bg-[#2B211E] text-[#C4A997]" : "bg-[#F5E6CC] text-[#5A3E36]"}`}>{b.status}</span>
              </span>
              <span className={`text-[12px] ${b.priority==="Cao" ? "text-[#FF8C42] font-semibold" : cfg.textMuted}`}>{b.priority}</span>
            </div>
          ))}
          <div className={`px-5 py-3 text-[11px] flex items-center gap-2 ${cfg.textMuted} ${isDark ? "bg-[#2B211E]" : "bg-[#FFF8F0]"}`}>
            <AlertCircle className="w-4 h-4 shrink-0" /> <span>Nếu bạn gặp lỗi, nhắn cho Mèo qua <a href={meta.fanpageUrl} target="_blank" rel="noopener" className="underline decoration-dotted">fanpage Facebook</a>, Mèo sẽ đọc mỗi tối trước khi ngủ.</span>
          </div>
        </div>
      </section>

      {/* Donate */}
      <section id="donate" className={`${isDark ? "bg-[#352A27] border-[#4A3A34]" : "bg-[#F5E6CC] border-[#E9DCC6]"} border-y py-14`}>
        <div className="mx-auto max-w-[1120px] px-5 md:px-8">
          <div className="grid md:grid-cols-[1.1fr_0.9fr] gap-8 items-start">
            <div>
              <div className="inline-flex items-center gap-2 mb-3">
                <Coffee className="w-5 h-5 text-[#FF8C42]" />
                <span className="text-[13px] font-semibold tracking-wider uppercase opacity-70">Donate cho Mèo</span>
              </div>
              <h2 className="display text-[28px] md:text-[32px] font-bold leading-tight">Mèo Mực làm app này vì mê sách, không vì tiền.</h2>
              <p className={`mt-3 text-[14px] leading-relaxed max-w-[52ch] ${cfg.textMuted}`}>
                Nhưng nếu bạn thấy chill hơn nhờ Mèo, có thể mời Mèo một ly cà phê. Mèo sẽ dùng để mua thêm sách, và cá khô. Mèo hứa không mua đồ ồn ào.
              </p>

              <div className="mt-6 flex flex-wrap gap-3">
                {donate.buymeacoffee && (
                  <a href={donate.buymeacoffee} target="_blank" rel="noopener" className="px-5 py-2.5 rounded-full bg-[#FF8C42] text-white text-[14px] font-semibold shadow hover:translate-y-[-1px] transition inline-flex items-center gap-2">
                    <Coffee className="w-4 h-4" /> Buy Me a Coffee
                  </a>
                )}
                {donate.momo && (
                  <span className={`px-5 py-2.5 rounded-full border text-[14px] font-semibold ${isDark ? "bg-[#3A2E2A] border-[#4A3A34] text-[#F5E6CC]" : "bg-white border-[#E9DCC6] text-[#5A3E36]"}`}>Momo: {donate.momo}</span>
                )}
                {donate.bank && (
                  <span className={`px-5 py-2.5 rounded-full border text-[14px] font-semibold ${isDark ? "bg-[#3A2E2A] border-[#4A3A34] text-[#F5E6CC]" : "bg-white border-[#E9DCC6] text-[#5A3E36]"}`}>{donate.bank}</span>
                )}
                <a href={meta.fanpageUrl} target="_blank" rel="noopener" className={`px-5 py-2.5 rounded-full border text-[14px] font-semibold inline-flex items-center gap-2 hover:translate-y-[-1px] transition ${isDark ? "bg-[#3A2E2A] border-[#4A3A34] text-[#F5E6CC]" : "bg-white border-[#E9DCC6] text-[#5A3E36]"}`}>
                  <Facebook className="w-4 h-4" /> Nhắn Mèo trên fanpage
                </a>
              </div>
            </div>

            <div className="relative">
              <div className={`rounded-[24px] p-6 border ${isDark ? "bg-[#3A2E2A] border-[#4A3A34]" : "bg-white border-[#F0E2C8] shadow-[0_16px_40px_rgba(90,62,54,0.1)]"}`}>
                <div className="flex items-center gap-3 mb-4">
                  <img src={logoUrl} alt="Mèo Mực" className="w-12 h-12 rounded-full bg-[#F5E6CC] p-1" />
                  <div>
                    <div className="font-bold text-[14px]">Lời nhắn của Mèo</div>
                    <div className={`text-[11px] ${cfg.textMuted}`}>gửi từ góc bàn, lúc {weather === "dem" ? "11:42 đêm" : "3:17 chiều"}</div>
                  </div>
                </div>
                <p className={`text-[13px] leading-relaxed ${cfg.textMuted}`}>
                  “Mình làm MewBook vì mình ghét cảm giác sách nằm lung tung trong máy. Mình muốn mở app lên, thấy kệ sách gọn gàng, ấm ấm, như phòng mình lúc mưa. Nếu bạn cũng thích cảm giác đó, mình vui rồi. Donate hay không cũng không sao, miễn là bạn đọc xong một cuốn sách mà bạn thích.”
                </p>
                <div className="mt-4 text-right">
                  <span className="font-bold text-[13px]">— Mèo Mực 🐾</span>
                </div>
              </div>

              {/* Donate QR: the image is deployed with the build but never committed (see .gitignore); without it, a note. */}
              {donate.qr && !qrMissing ? (
                <div className={`mt-4 rounded-[16px] p-4 border text-center ${isDark ? "border-[#4A3A34] bg-[#2B211E]" : "border-[#F0E2C8] bg-white shadow-sm"}`}>
                  <img src={donate.qr} alt="Mã QR ủng hộ Mèo Mực (VietQR)" onError={() => setQrMissing(true)} className="mx-auto w-full max-w-[260px] rounded-[12px]" />
                  <div className={`mt-2 text-[11px] ${cfg.textMuted}`}>Quét bằng app ngân hàng bất kỳ. Cảm ơn bạn đã mời Mèo cà phê ☕</div>
                </div>
              ) : (
                <div className={`mt-4 rounded-[16px] p-4 border-dashed border-2 grid place-items-center h-[120px] text-center ${isDark ? "border-[#4A3A34] text-[#C4A997] bg-[#2B211E]" : "border-[#E9DCC6] text-[#9A7E6E] bg-[#FFF8F0]"}`}>
                  <div className="text-[11px]">Mã QR ủng hộ sẽ có ở đây<br />Mèo đang vẽ...</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className={`py-10 ${isDark ? "bg-[#2B211E] text-[#C4A997]" : "bg-[#FFF8F0] text-[#8B6B5E]"} transition-colors duration-700`}>
        <div className="mx-auto max-w-[1120px] px-5 md:px-8">
          <div className="flex flex-col md:flex-row justify-between gap-6">
            <div className="flex items-center gap-3">
              <img src={logoUrl} alt="Mèo Mực logo" className="w-9 h-9 rounded-full bg-[#F5E6CC] p-1" />
              <div>
                <div className={`font-bold ${isDark ? "text-[#F5E6CC]" : "text-[#5A3E36]"}`}>Mèo Mực @meomuc.mewbook</div>
                <div className="text-[12px]">facebook.com/meomuc.mewbook</div>
              </div>
            </div>
            <div className="text-[12px] leading-relaxed max-w-[36ch]">
              Made with love by <b className={isDark ? "text-[#F5E6CC]" : "text-[#5A3E36]"}>Anh Tiên Sinh</b> — một người hướng nội thích mèo mập ngồi sau lưng.<br />
              <span className="opacity-70">Phần mềm miễn phí, mã nguồn mở (AGPL-3.0), không thu thập dữ liệu. Đọc sách dễ hơn, sống chill hơn.</span>
            </div>
          </div>
          <div className="mt-8 pt-6 border-t border-dashed flex items-center justify-between text-[11px] opacity-60">
            <span>© 2026 Mèo Mực — MewBook. Chubby cat from behind, always.</span>
            <span className="hidden sm:inline">{latest?.ver} • paper texture • weather-reactive • local-first</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
