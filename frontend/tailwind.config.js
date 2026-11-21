/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Kantumruy Pro', 'system-ui', 'sans-serif'],
        display: ['Inter', 'Kantumruy Pro', 'system-ui', 'sans-serif'],
        khmer: ['Kantumruy Pro', 'Noto Sans Khmer', 'sans-serif'],
      },
      colors: {
        ink: {
          950: '#07090d',
          900: '#0b0e14',
          850: '#10141c',
          800: '#151a24',
          700: '#202735',
        },
        gold: {
          300: '#ffdb8a',
          400: '#f7c457',
          500: '#e9a92d',
        },
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(247,196,87,.18), 0 24px 80px -30px rgba(247,196,87,.3)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'soft-pulse': {
          '0%, 100%': { opacity: '.45', transform: 'scaleY(.55)' },
          '50%': { opacity: '1', transform: 'scaleY(1)' },
        },
      },
      animation: {
        'fade-up': 'fade-up .5s ease-out both',
        'soft-pulse': 'soft-pulse 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
