# Third-party notices

No third-party source code has been copied into this repository. Dependencies are installed
from package registries and keep their own licences:

- Backend: see `backend/uv.lock` (FastAPI, SQLAlchemy, Alembic, Pydantic, psycopg, Celery,
  argon2-cffi, openpyxl, uvicorn and their dependencies — permissive licences: MIT, BSD, Apache-2.0,
  LGPL for psycopg).
- Frontend: see `frontend/package-lock.json` (Next.js, React, Tailwind CSS, Playwright and
  dependencies — MIT / Apache-2.0).

Reviewed but not copied (for reference and possible future reuse):
- `strelov1/freehire` @ `ec6e65f7bc165d690970e7a5b902f35bf5b49c27`, MIT, © 2026 freehire contributors.
  If code is ever copied, its copyright and permission notice must be included here. The MIT
  licence does not cover the job postings it serves.
- `morluto/rea` @ `b4938aed58737293a6987630476632619713f5cd` (`rea-agents@6.7.0`), MIT. A
  development-time tool only; not distributed with NoEfforts.

Job content, employer trademarks and third-party services are not licensed by any of the above.
