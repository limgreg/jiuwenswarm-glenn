# Demo project brief: Shelfie — a tiny book-club tracker

Paste everything below the line into a JiuwenSwarm **Team** session.

---

Use the fullstack-devco-swarm skill in build mode.

project_dir: /ABSOLUTE/PATH/TO/shelfie        <- change this to an empty folder on your machine
stack: FastAPI + SQLite (SQLModel) + React/TypeScript (Vite) + Docker Compose
max_fix_rounds: 2

Build "Shelfie", a small web app for book clubs:

1. People sign up and log in with email + password.
2. A user can create a club and invite others with a join code.
3. Club members add books to the club's shelf (title, author, optional cover URL).
4. Members vote on which shelf book to read next — one vote per member per round;
   the club owner closes the round and the winner becomes "currently reading".
5. Each member can mark their progress on the current book (0–100%) and see
   everyone else's progress on the club page.
6. Only the club owner can remove books, close a voting round or delete the club.

Keep it small: no email sending, no payments, no social login. It must run locally
with one `docker compose up`, and have automated backend and frontend tests.
