## Knowledge Base (lore)

On session start, read `.pi/kb/CONTEXT.md`. If it references `@workspace`, read `../.pikb/MAP.md`.

During work:
- Writing code → check `.pikb/CONVENTIONS.md`
- Multi-module changes → check `.pikb/MAP.md`
- Error encountered → check `.pikb/PITFALLS.md` or `.pi/kb/PITFALLS.md`
- Significant change complete → ask user if kb should be updated

If `.pikb/` doesn't exist and the project appears complex:
- Explore the codebase
- Ask the user to fill gaps
- Generate initial `.pikb/` files from templates in `lore/templates/`
