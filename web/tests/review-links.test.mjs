import assert from "node:assert/strict";
import test from "node:test";
import { buildReviewLink, parseReviewLink } from "../lib/review-links.js";

const reference = "a".repeat(32);
const candidate = "b".repeat(32);

test("builds and restores a comparison review link", () => {
  const link = buildReviewLink("https://rootsignal.example/workspace?old=value#top", reference, candidate);
  const url = new URL(link);
  assert.equal(url.hash, "#runs");
  assert.deepEqual(parseReviewLink(url.search), {
    referenceRunId: reference,
    candidateRunId: candidate,
  });
  assert.equal(url.searchParams.has("old"), false);
});

test("rejects malformed, incomplete, and identical run pairs", () => {
  assert.equal(parseReviewLink("?run=not-a-run&compare_to=also-invalid"), null);
  assert.equal(parseReviewLink(`?run=${reference}`), null);
  assert.equal(parseReviewLink(`?run=${reference}&compare_to=${reference}`), null);
  assert.throws(() => buildReviewLink("https://rootsignal.example", reference, reference));
});
