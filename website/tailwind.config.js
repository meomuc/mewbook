// SPDX-License-Identifier: AGPL-3.0-or-later
// content.json is scanned too: the version tags and bug dots carry Tailwind classes ("bg-emerald-500"),
// so the update script can change them without touching the UI code.
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./*.{ts,tsx}", "./content.json"],
  theme: { extend: {} },
  plugins: [],
};
