/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          bg: '#0B0E14',
          card: '#151921',
          border: '#2A2F3D',
          hover: '#1E2330'
        },
        financial: {
          green: '#089981',
          red: '#F23645',
          amber: '#F59E0B',
          blue: '#2962FF',
          accent: '#7C3AED'
        }
      }
    },
  },
  plugins: [],
}
