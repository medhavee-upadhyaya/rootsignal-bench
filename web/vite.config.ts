import vinext from "vinext";
import { nitro } from "nitro/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vinext(), nitro()],
});
