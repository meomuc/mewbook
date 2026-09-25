// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Picks the page's weather theme (nang / mua / may / dem) from the visitor's real weather.
 *
 * Order: browser geolocation -> Open-Meteo (keyless, CORS-enabled) -> WMO weather code. When the visitor
 * declines location, or the request fails, we fall back to the local clock (night after 18:00) so the page
 * never waits on the network. Privacy: coordinates are rounded to ~11 km before the request, are sent only to
 * Open-Meteo, and are never stored; only the resulting theme key is cached (30 minutes) in localStorage.
 */

export type WeatherKey = "nang" | "mua" | "may" | "dem";

const CACHE_KEY = "mewbook.weather.v1";
const CACHE_MS = 30 * 60 * 1000;
const GEO_TIMEOUT_MS = 8000;
const FETCH_TIMEOUT_MS = 6000;

/** WMO weather interpretation codes (https://open-meteo.com/en/docs) -> theme. */
export function themeFromWeather(code: number, isDay: boolean, cloudCover: number): WeatherKey {
  if (!isDay) return "dem";
  const wet = (code >= 51 && code <= 67) || (code >= 80 && code <= 82) || code >= 95;
  if (wet) return "mua";
  const grey = code === 3 || code === 45 || code === 48 || (code >= 71 && code <= 77) || code === 85 || code === 86;
  if (grey || cloudCover >= 70) return "may";
  return "nang";
}

/** Offline fallback: only day vs. night is knowable from the clock. */
export function themeFromClock(now: Date = new Date()): WeatherKey {
  const h = now.getHours();
  return h >= 18 || h < 5 ? "dem" : "nang";
}

function readCache(): WeatherKey | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const { key, at } = JSON.parse(raw) as { key: WeatherKey; at: number };
    return Date.now() - at < CACHE_MS ? key : null;
  } catch {
    return null;
  }
}

function writeCache(key: WeatherKey): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ key, at: Date.now() }));
  } catch {
    /* private mode: caching is optional */
  }
}

function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) return reject(new Error("no geolocation"));
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      timeout: GEO_TIMEOUT_MS,
      maximumAge: CACHE_MS,
      enableHighAccuracy: false,
    });
  });
}

async function locationDenied(): Promise<boolean> {
  try {
    const status = await navigator.permissions?.query({ name: "geolocation" as PermissionName });
    return status?.state === "denied";
  } catch {
    return false;
  }
}

/** Resolves the theme for the visitor's place, or null when it cannot be determined (caller uses the clock). */
export async function detectWeather(): Promise<WeatherKey | null> {
  const cached = readCache();
  if (cached) return cached;
  if (await locationDenied()) return null;
  try {
    const pos = await getPosition();
    const lat = pos.coords.latitude.toFixed(1);
    const lon = pos.coords.longitude.toFixed(1);
    const url =
      `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
      "&current=weather_code,is_day,cloud_cover&timezone=auto";
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(url, { signal: ctl.signal });
      if (!res.ok) return null;
      const cur = (await res.json()).current as { weather_code: number; is_day: number; cloud_cover: number };
      const key = themeFromWeather(cur.weather_code, cur.is_day === 1, cur.cloud_cover);
      writeCache(key);
      return key;
    } finally {
      clearTimeout(timer);
    }
  } catch {
    return null;
  }
}
