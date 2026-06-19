# Papaya

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

| 🌐 Language |
|-------------|
| [🇷🇺 Russian](README.md) • [🇬🇧 English](English.md) |

## Content

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [API & Routes](#api--routes)
- [License](#license)

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

## Quick Start

### 1. Clone the Repository

***Make sure VPN is disabled***

Clone the project. Launch Docker Desktop and navigate to its directory:

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd ./path/to/Papaya
```

### 2. Run the Application

Build and start the containers:

```bash
docker-compose up -d --build
```

After successful startup, the application will be available at:
[http://localhost:5000](http://localhost:5000)

To view application logs in real-time:

```bash
docker-compose logs -f
```

### 3. Stop and Cleanup

To stop the services:
```bash
docker-compose down
```

To stop services and remove database volumes (all user data and events will be permanently deleted):
```bash
docker-compose down -v
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
