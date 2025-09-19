/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    // Templates in your Django project
    '../../**/templates/**/*.html',
    '../../**/templates/**/*.py',  
    // JavaScript files that might contain Tailwind classes
    './js/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Albert Sans', 'system-ui', 'sans-serif'], // This makes Albert Sans your default font
      },
    },
  },
  plugins: [
    require("daisyui"),
  ],
  daisyui: {
    themes: [
      "corporate",
      "dark",
      {
        "lacos": {
          "primary": "#3b82f6",
          "secondary": "#1e40af",
          "accent": "#06b6d4",
          "neutral": "#32475b",  // Your navbar color
          "base-100": "#ffffff",
          "base-200": "#f9fafb",
          "base-300": "#32475b", // Use your color for navbar background
          "info": "#3abff8",
          "success": "#36d399",
          "warning": "#fbbd23",
          "error": "#f87272",
        },
      },
    ],
  },
}
