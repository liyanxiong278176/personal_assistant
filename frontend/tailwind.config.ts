import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
        display: ['"Cormorant Garamond"', "Georgia", "serif"],
        heading: ['"Fraunces"', "Georgia", "serif"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        // Twilight palette
        twilight: {
          deep: "hsl(var(--twilight-deep))",
          mid: "hsl(var(--twilight-mid))",
          soft: "hsl(var(--twilight-soft))",
          glow: "hsl(var(--twilight-glow))",
        },
        // Warm accent palette
        ember: {
          DEFAULT: "hsl(var(--ember))",
          light: "hsl(var(--ember-light))",
          dark: "hsl(var(--ember-dark))",
        },
        sand: {
          DEFAULT: "hsl(var(--sand))",
          light: "hsl(var(--sand-light))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "calc(var(--radius) + 4px)",
        "2xl": "calc(var(--radius) + 8px)",
      },
      animation: {
        "slide-in-left": "slideInLeft 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right": "slideInRight 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-up": "slideInUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in": "fadeIn 0.3s ease-out",
        "fade-in-up": "fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
        "float": "float 6s ease-in-out infinite",
        "float-slow": "floatSlow 8s ease-in-out infinite",
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
        "spin-slow": "spin 12s linear infinite",
        "typing-bounce": "typingBounce 1.4s ease-in-out infinite",
        "shimmer": "shimmer 2.5s linear infinite",
        "scale-in": "scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        "page-enter": "pageEnter 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
        "breathing": "breathing 4s ease-in-out infinite",
      },
      keyframes: {
        slideInLeft: {
          from: { opacity: "0", transform: "translateX(-24px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        slideInRight: {
          from: { opacity: "0", transform: "translateX(24px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        slideInUp: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        fadeInUp: {
          from: { opacity: "0", transform: "translateY(20px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px) rotate(0deg)" },
          "33%": { transform: "translateY(-8px) rotate(1deg)" },
          "66%": { transform: "translateY(-4px) rotate(-1deg)" },
        },
        floatSlow: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.6", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.05)" },
        },
        typingBounce: {
          "0%, 80%, 100%": { transform: "scale(0.8)", opacity: "0.5" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        scaleIn: {
          from: { opacity: "0", transform: "scale(0.9)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        pageEnter: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        breathing: {
          "0%, 100%": { transform: "scale(1)", opacity: "0.8" },
          "50%": { transform: "scale(1.03)", opacity: "1" },
        },
      },
      backgroundImage: {
        "gradient-twilight": "linear-gradient(135deg, hsl(var(--twilight-deep)) 0%, hsl(var(--twilight-mid)) 50%, hsl(var(--twilight-soft)) 100%)",
        "gradient-ember": "linear-gradient(135deg, hsl(var(--ember)) 0%, hsl(var(--sand)) 100%)",
        "gradient-sky": "linear-gradient(180deg, hsl(var(--twilight-soft)) 0%, hsl(var(--background)) 100%)",
        "gradient-radial": "radial-gradient(ellipse at center, hsl(var(--twilight-glow)) 0%, transparent 70%)",
        "gradient-card": "linear-gradient(145deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.6) 100%)",
        "gradient-card-dark": "linear-gradient(145deg, rgba(30,40,60,0.9) 0%, rgba(20,30,50,0.7) 100%)",
        "gradient-header": "linear-gradient(135deg, hsl(var(--twilight-deep) / 0.9) 0%, hsl(var(--twilight-mid) / 0.8) 100%)",
      },
      boxShadow: {
        "soft": "0 2px 20px rgba(30, 40, 60, 0.08)",
        "soft-lg": "0 8px 40px rgba(30, 40, 60, 0.12)",
        "soft-xl": "0 16px 60px rgba(30, 40, 60, 0.15)",
        "glow": "0 0 30px rgba(194, 140, 90, 0.25)",
        "glow-sm": "0 0 15px rgba(194, 140, 90, 0.15)",
        "glow-primary": "0 4px 20px rgba(55, 90, 140, 0.2)",
        "ember": "0 4px 20px rgba(194, 140, 90, 0.3)",
        "glass": "0 8px 32px rgba(30, 40, 60, 0.12), inset 0 1px 0 rgba(255,255,255,0.4)",
        "inner-soft": "inset 0 2px 8px rgba(30, 40, 60, 0.06)",
        "card-hover": "0 20px 60px rgba(30, 40, 60, 0.15)",
      },
      backdropBlur: {
        xs: "2px",
      },
      transitionTimingFunction: {
        "expressive": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
