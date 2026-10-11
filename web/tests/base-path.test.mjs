import assert from "node:assert/strict";
import test from "node:test";

import { appPath, normalizeBasePath } from "../lib/base-path.js";

test("normalizes deployment prefixes", () => {
  assert.equal(normalizeBasePath(""), "");
  assert.equal(normalizeBasePath("/"), "");
  assert.equal(normalizeBasePath("project/rootsignalbench/"), "/project/rootsignalbench");
  assert.equal(normalizeBasePath("//project/rootsignalbench//"), "/project/rootsignalbench");
});

test("keeps root deployments backwards compatible", () => {
  assert.equal(appPath("/api/incidents"), "/api/incidents");
  assert.equal(appPath("api/runs?limit=20"), "/api/runs?limit=20");
});
