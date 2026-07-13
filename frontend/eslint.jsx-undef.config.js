/**
 * Build gate: only undeclared JSX components (missing imports).
 * Kept separate so existing lint debt does not block `npm run build`.
 */
import globals from "globals"
import reactHooks from "eslint-plugin-react-hooks"
import { defineConfig, globalIgnores } from "eslint/config"
import jsxNoUndef from "./eslint-rules/jsx-no-undef.js"

export default defineConfig([
  globalIgnores(["dist", "node_modules"]),
  {
    files: ["src/**/*.{js,jsx}"],
    plugins: {
      // Present so inline `eslint-disable-line react-hooks/...` comments resolve.
      "react-hooks": reactHooks,
      local: { rules: { "jsx-no-undef": jsxNoUndef } },
    },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    linterOptions: {
      reportUnusedDisableDirectives: "off",
    },
    rules: {
      "local/jsx-no-undef": "error",
    },
  },
])
