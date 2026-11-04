/** Config do Tailwind para o Chronos */
module.exports = {
  darkMode: "class",
  content: ["./app/templates/**/*.html", "./app/main.py"],
  theme: {
    extend: {
      colors: {
        /* Verde-Petróleo (primário da marca) — guidas: chronos-brand-guidelines.md */
        brand: {
          50: "#eef5f6",
          100: "#d7e7e8",
          200: "#b0cfd1",
          300: "#83b0b4",
          400: "#4c8389",
          500: "#1d6f74",
          600: "#0B555A",
          700: "#0a474c",
          800: "#093a3d",
          900: "#08292c",
        },
        /* Verde Saldo Positivo — indicadores de horas positivas */
        positive: {
          50: "#eaf6f2",
          100: "#cfeae0",
          200: "#a2d9c4",
          300: "#6cc1a4",
          400: "#3aa486",
          500: "#12805C",
          600: "#106e50",
          700: "#0d5a41",
          800: "#0a4633",
          900: "#073225",
        },
        /* Coral Impulso — chevron da marca, CTAs e destaques */
        coral: {
          50: "#fdf1ec",
          100: "#fae0d5",
          200: "#f5bda6",
          300: "#ee9877",
          400: "#FF7A52",
          500: "#D94E28",
          600: "#bc4020",
          700: "#97331a",
          800: "#7a2a17",
          900: "#5c2010",
        },
        /* Areia Suave — fundos secundários acolhedores */
        sand: {
          DEFAULT: "#F6F5F0",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        /* Títulos e números de saldo/horas — guia da marca, seção 5 */
        display: ["Plus Jakarta Sans", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        subtle: "0 1px 3px 0 rgba(0,0,0,0.05), 0 1px 2px 0 rgba(0,0,0,0.03)",
        card: "0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)",
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
