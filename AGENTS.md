## Knowledge Base (lore)

On session start:
1. Read `.pi/kb/CONTEXT.md`
2. If it references `@workspace`, read `../.pikb/MAP.md`

During work:
- Writing code → check `.pikb/CONVENTIONS.md`
- Multi-module changes → check `.pikb/MAP.md`
- Error encountered → check `.pikb/PITFALLS.md` or `.pi/kb/PITFALLS.md`
- New repo discovered → create `.pi/kb/CONTEXT.md`
- Significant change → ask user: "knowledge base 需要更新吗？"

If `.pikb/` doesn't exist and project looks complex (multi-repo / >5 rounds):
1. Explore codebase structure
2. Present findings, ask user to fill gaps
3. Generate from `lore/templates/`
4. Cover EVERY repo with CONTEXT.md
