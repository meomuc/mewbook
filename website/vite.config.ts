// SPDX-License-Identifier: AGPL-3.0-or-later
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// VITE_BASE is the address prefix the site is served under: "/" on its own domain (the default), and
// "/mewbook-landing/" on a GitHub Pages project address (set by .github/workflows/deploy.yml).
export default defineConfig({ base: process.env.VITE_BASE ?? "/", plugins: [react()] });
