// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*"],
    rules: {
      // Data-fetching hooks intentionally expose loading/idle transitions.
      "react-hooks/set-state-in-effect": "off",
      // React Native Animated values are stable imperative handles.
      "react-hooks/refs": "off",
      "import/no-named-as-default-member": "off",
    },
  }
]);
