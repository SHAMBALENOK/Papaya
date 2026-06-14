# Papaya

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

| 🌐 Language |
|-------------|
| [🇷🇺 Russian](README.md) • [🇬🇧 English](English.md) |

Papaya is a web service for school students that consolidates information about nationwide and regional academic competitions in one convenient platform. The platform allows users to register, manage their profiles, and explore educational events.

Demo version of the project is available at: https://papaya-poxq.onrender.com

## Features

- **Authentication & Registration:** Secure login system with password hashing and data validation.
- `COMING SOON` **JWT Authentication:** Authentication mechanism will soon be migrated to JWT.
- **Competitions Catalog:** Browse a list of active academic events and olympiads.
- **Profile Editing:** Users can update their personal information on a dedicated profile page.
- **Event Creation & Editing:** Ability to create and edit events.
- `COMING SOON` **Event Management Improvements:** The mechanism for updating and adding events will change, along with the interface and possibly the management page.
- `NEW` **Table Import:** Users can insert olympiad information directly from PDF tables.
- `NEW` **Auto-setup:** The web service can be configured using **setup.bat/setup.sh** (downloads AI model for table recognition).
- `COMING SOON` **Roles & Tabs:** User roles (student/teacher/educational organization) with different capabilities and categorized event tabs coming soon.
- `COMING SOON` **Administration Panel:** Convenient web-based administration panel coming soon.
- `COMING SOON` **Free Access:** Ability to use certain pages without authentication.

## Technology Stack

- **Backend:** Python, Flask, Flask-Login
- **Database:** PostgreSQL, SQLAlchemy (ORM)
- **Containerization:** Docker, Docker Compose
- **Templates:** Jinja2
- **Security:** Password hashing, regex-based validation, UUID for user identifiers.

## Prerequisites

Before getting started, ensure your system has the following components installed:

- **Git** (for cloning the repository)
- **Docker** version 20.10 or higher
- **Docker Compose** version 2.0 or higher
- Internet access (required for downloading Docker images and connecting to remote databases if using cloud hosting)

## Quick Start (DOCKER branch only)

### 1. Clone the Repository

Clone the project and navigate to its directory:

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd Papaya
```

### 2. Configure Environment Variables

Create a `.env` file in the project root directory.

Create a `.env` file with the following content (replace values with your own or use the examples for local testing):

```ini
# Application secret keys
# Generate unique keys using: python -c "import secrets; print(secrets.token_urlsafe(48))"
FLASK_SECRET_KEY=your_flask_secret_key
JWT_SECRET_KEY=your_jwt_secret_key

# Database connection settings
# For local docker-compose deployment, the values below are typically used:
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=postgres
DB_PORT=5432
DB_NAME=testdb

# Variables for initializing a test event on first run
INIT_EVENT_ID=111
INIT_EVENT_NAME=my_event
INIT_EVENT_PLACE=my_place
INIT_EVENT_MIN_GRADE=1
INIT_EVENT_MAX_GRADE=11
INIT_EVENT_MIN_AGE=6
INIT_EVENT_MAX_AGE=17

# Alternatively, use a full database connection URL
# Used for connecting to remote databases (e.g., Render, Neon)
# DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require
```

### 3. Run the Application

Ensure Docker Desktop is running. Then build and start the containers:

```bash
docker-compose up -d --build
```

After successful startup, the application will be available at:
[http://localhost:5000](http://localhost:5000)

To view application logs in real-time:

```bash
docker-compose logs -f
```

### 4. Stop and Cleanup

To stop the services:
```bash
docker-compose down
```

To stop services and remove database volumes (all user data and events will be permanently deleted):
```bash
docker-compose down -v
```

## Project Structure

```text
Papaya/
├── .env                  # Environment variables 
├── .gitignore            # Git ignore rules
├── main.py               # Main application entry point
├── database/
│   ├── __init__.py
│   └── database.py       # SQLAlchemy models (Users, Events), migrations, and database access functions
├── middlewares/
│   ├── __init__.py
│   ├── parse.py          # Parsing utilities (for future projects)
│   ├── re_check.py       # Data validation (email, password, name) via regular expressions
│   └── tokenz.py         # Token handling logic
├── templates/
│   ├── auth.html         # Login and registration page
│   ├── main.html         # Main page with event list
│   ├── event_detail.html # Event detail view template
│   └── RottedPapaya.html # Additional templates
└── docker-compose.yml    # Docker container configuration (App + Postgres)
```

## API & Routes

Main application endpoints:

| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/auth` | Authentication/registration page | Public |
| `POST` | `/auth/register` | Register a new user | Public |
| `POST` | `/auth/login` | User login | Public |
| `GET` | `/logout` | User logout | Authenticated |
| `GET` | `/` | Main page with olympiad list | Authenticated |
| `GET` | `/event/<id>` | Event/olympiad details | Authenticated |
| `GET` | `/user/<user_id>` | User profile details | Authenticated |
| `POST` | `/user/<user_id>/edit_info` | Edit user profile | Authenticated |
| `POST` | `/user/<user_id>/add_event` | Create new event | Authenticated |
| `POST` | `/user/<user_id>/<event_id>/edit_event` | Edit event | Authenticated |
| `POST` | `/user/<user_id>/add_events_via_pdf_tables` | Import events from PDF tables | Authenticated |

## License

This project is distributed under the MIT License.
