/** @type {import('next').NextConfig} */
const nextConfig = {
  // Don't auto-generate AGENTS.md/CLAUDE.md — this project already has
  // its own root CLAUDE.md as the canonical instruction file.
  agentRules: false,
};

module.exports = nextConfig;
