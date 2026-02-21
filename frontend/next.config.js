/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  env: {
    // Public URL used by browser (client-side) requests
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  async rewrites() {
    // Internal URL for server-side rewrites (Docker: http://app:8000, local: http://localhost:8000)
    const internalApi = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${internalApi}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
