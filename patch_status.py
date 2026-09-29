
with open("docs/IMPLEMENTATION_STATUS.md") as f:
    content = f.read()

content = content.replace("M5.1 implemented, fully verified, and ready for independent review.", "M5.2 implemented, awaiting review.")
content = content.replace("Milestone M5.1 HEAD", "Milestone M5.2 HEAD")
content = content.replace("commit\n- `147862f` (Milestone M5.1 HEAD)", "commit\n- `HEAD` (Milestone M5.2 in progress)")
content = content.replace("**Review verdict (2026-09-29): M5 FAIL — focused M5.1 required.**", "**Review verdict (2026-09-29): M5 FAIL — focused M5.1 required.**\n**Review verdict (2026-09-29): M5.1 FAIL — focused M5.2 required.**")
content = content.replace("**Current review target:** Milestone M5.1", "**Current review target:** Milestone M5.2")
content = content.replace("M5.1 state", "M5.2 state")

with open("docs/IMPLEMENTATION_STATUS.md", "w") as f:
    f.write(content)

