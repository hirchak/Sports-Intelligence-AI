with open("src/sports_intelligence/api/routes/research.py") as f:
    content = f.read()

content = content.replace("from typing import Annotated, Literal\n\nfrom fastapi", "from typing import Annotated, Literal\nfrom uuid import UUID\n\nfrom fastapi")

with open("src/sports_intelligence/api/routes/research.py", "w") as f:
    f.write(content)
