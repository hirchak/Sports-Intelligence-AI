with open(".env.example") as f:
    content = f.read()

content = content.replace("RESEARCH_ENABLED=true\n", "RESEARCH_ENABLED=true\nRESEARCH_CLAIM_EXTRACTION_ENABLED=true\n")

with open(".env.example", "w") as f:
    f.write(content)
