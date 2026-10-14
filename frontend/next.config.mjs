/** Browser requests stay on the site origin. Workspace routes retain their own proxy. */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const api = process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000';
    const endpoints = ['historical', 'multi-horizon-validation', 'validation', 'shap', 'latest', 'data-health', 'korea/shap', 'korea/historical', 'korea/validation', 'korea/latest'];
    return endpoints.map(path => ({ source: `/api/${path}`, destination: `${api}/api/${path}` }));
  },
};
export default nextConfig;
