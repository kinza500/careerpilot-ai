import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#0f766e", dark: "#134e4a", light: "#5eead4" },
      },
    },
  },
  plugins: [],
};
export default config;
