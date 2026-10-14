// Runs webui/js/modules/models_presets.js in node: argv[2] the module's URL, argv[3] the cases as JSON.
const { choiceOf, bestRoles } = await import(process.argv[2]);
const cases = JSON.parse(process.argv[3]);
const out = {};
for (const [name, c] of Object.entries(cases)) out[name] = c.best ? bestRoles(c.roles, c.provider, c.model) : choiceOf(c.roles, c.mode);
console.log(JSON.stringify(out));
