/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend asset images are served from the FastAPI app; allow <img> from it.
  images: { unoptimized: true },
  // No ESLint config is shipped (keeps deps minimal); TypeScript checking stays ON.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
