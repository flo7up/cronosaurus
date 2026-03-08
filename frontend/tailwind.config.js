/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      keyframes: {
        glow: {
          "0%, 100%": { borderColor: "rgba(217, 119, 6, 0.3)", boxShadow: "0 0 4px rgba(217, 119, 6, 0.1)" },
          "50%": { borderColor: "rgba(245, 158, 11, 0.6)", boxShadow: "0 0 12px rgba(245, 158, 11, 0.2)" },
        },
      },
    },
  },
  plugins: [],
};
