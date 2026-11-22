// Runs webui/js/modules/chat_sources.js in node (no localStorage: the page's own copy): argv[2] the module's URL.
const { sourcesChoice, toggleSource, sourcesBadge } = await import(process.argv[2]);
const out = { start: [...sourcesChoice()] };
out.one = [...toggleSource("legal")];
out.two = [...toggleSource("medicine")];
out.badge2 = sourcesBadge();
out.three = [...toggleSource("science")];
out.badge3 = sourcesBadge();
out.off = [...toggleSource("medicine")];
out.auto = [...toggleSource("auto")];
out.badge0 = sourcesBadge();
console.log(JSON.stringify(out));
