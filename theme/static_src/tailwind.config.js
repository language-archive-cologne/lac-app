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
    themes: ["corporate", "dark"], // You can customize themes here
  },
}
