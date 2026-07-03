// Behavioral tests for the direct slide editor's pure core: the path engine
// (_getAt/_setAt) and the type router (isItemsArray/isObjArray) that decide how each
// content key is edited. These are DOM-free one-liners in dashboard/index.html; we
// extract and eval them so the test exercises the SHIPPED code, not a copy.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const HTML = fs.readFileSync(path.join(__dirname, "..", "dashboard", "index.html"), "utf8");
const SCRIPT = HTML.split("<script>")[1].split("</script>")[0];

// pull a single-line `function NAME(...){...}` definition verbatim from the source
function grab(name) {
  const re = new RegExp("^function " + name + "\\(.*\\}$", "m");
  const m = SCRIPT.match(re);
  if (!m) throw new Error("could not extract " + name);
  return m[0];
}

const NAMES = ["escAttr", "humanKey", "_allStr", "isItemsArray", "isObjArray", "_getAt", "_setAt"];
const sandbox = { esc: (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])) };
vm.createContext(sandbox);
vm.runInContext(NAMES.map(grab).join("\n") + "\n;this.__e={" + NAMES.join(",") + "};", sandbox);
const E = sandbox.__e;

test("_getAt / _setAt walk dotted paths including array indices", () => {
  const o = { left: { items: ["a", "b"] }, steps: [{ title: "x" }, { title: "y" }] };
  assert.strictEqual(E._getAt(o, "left.items.1"), "b");
  assert.strictEqual(E._getAt(o, "steps.0.title"), "x");
  E._setAt(o, "steps.1.title", "Z");
  assert.strictEqual(o.steps[1].title, "Z");
  E._setAt(o, "left.items.0", "A");
  assert.strictEqual(o.left.items[0], "A");
});

test("isItemsArray recognizes string lists and bold-lead pairs", () => {
  assert.ok(E.isItemsArray(["a", "b"]));
  assert.ok(E.isItemsArray([["lead", " rest"], "plain"]));
  assert.ok(E.isItemsArray([]));                         // empty list reads as an items list
  assert.ok(!E.isItemsArray([{ title: "x" }]));          // object list is NOT an items list
});

test("isObjArray recognizes lists of objects only", () => {
  assert.ok(E.isObjArray([{ title: "x" }, { title: "y" }]));
  assert.ok(!E.isObjArray([]));                          // empty -> not an object list
  assert.ok(!E.isObjArray(["a"]));
  assert.ok(!E.isObjArray([["lead", "rest"]]));          // arrays are not objects
});

test("escAttr escapes quotes for attribute context", () => {
  assert.strictEqual(E.escAttr('he said "hi" <b>'), "he said &quot;hi&quot; &lt;b&gt;");
});

test("humanKey titlecases keys", () => {
  assert.strictEqual(E.humanKey("sub_label"), "Sub Label");
  assert.strictEqual(E.humanKey("title"), "Title");
});
