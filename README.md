# Nexly — Elite Tech DNA & Mastery Platform

[![Django](https://img.shields.io/badge/Backend-Django%204.2-092e20?style=for-the-badge&logo=django)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/API-REST%20Framework-ff1709?style=for-the-badge&logo=django)](https://www.django-rest-framework.org/)
[![Celery](https://img.shields.io/badge/Async-Celery-37814a?style=for-the-badge&logo=celery)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Cache-Redis-d82c20?style=for-the-badge&logo=redis)](https://redis.io/)

Nexly is a technical learning platform that uses data-driven performance metrics to verify and certify technical skills. It transforms standard course assessments into deep-skill profiles for career growth.

---

## 🏁 Quick Start

### 1. Initialize the Environment
```bash
pip install -r requirements.txt
python manage.py migrate
```

### 2. Launch the Ecosystem
You will need three terminal windows to run the full stack:

*   **Terminal 1 (Redis):** `redis-server`
*   **Terminal 2 (Core Server):** `python manage.py runserver`
*   **Terminal 3 (Async Worker):** `celery -A myproject worker -l info`

Access the platform at: `http://127.0.0.1:8000/`

---

## 📋 Prerequisites
- **Python 3.10+**: [Download](https://www.python.org/downloads/)
- **Redis**: [Installation Guide](https://redis.io/docs/getting-started/installation/)
- **SQLite** (default, local dev) / **PostgreSQL** (recommended for production)

---

## ⚙️ Environment Variables
Create a `.env` file in the root directory:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SECRET_KEY` | Django security key | (Required) |
| `DEBUG` | Enable/Disable debug mode | `True` |
| `DATABASE_URL` | Database connection string | `sqlite:///db.sqlite3` |
| `REDIS_URL` | Redis server address | `redis://localhost:6379/0` |

---

## 🚀 The Advantage

### 🧬 Skill DNA Profiling
Real-time performance metrics visualized via **Chart.js Radar Analytics**. It maps Accuracy, Speed, Consistency, Focus, and Mastery into a unique professional fingerprint.

### 🛡️ Proctoring
A dedicated, high-stakes assessment environment featuring:
- **Full-Screen Enforcement:** Strict browser locking to prevent tab-switching.
- **Server-Side Validation:** Time-windowed session tokens to verify submission integrity.
- **Progress Autosave:** Silent background engine saves progress every 5 seconds.

### 💼 Talent Marketplace
A **Recruiter Portal** allowing hiring managers to source top-performing candidates based on raw performance data.

### 🏗️ Advanced Core
- **Asynchronous Engine:** Background certificate generation via Celery.
- **Interactive Docs:** Full OpenAPI 3.0 (Swagger) documentation.

---

## 🛠️ Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Backend** | Django 4.2, Python 3.10+ |
| **API** | Django REST Framework (DRF) |
| **Async Tasks** | Celery + Redis |
| **Frontend** | Bootstrap 5, Chart.js, Vanilla JS |
| **Documentation** | drf-spectacular (Swagger UI) |

---

## 🔌 API Endpoints (Selection)

| Method | URL | Description |
| :--- | :--- | :--- |
| `GET` | `/onlinecourse/api/courses/` | List all available technical courses |
| `GET` | `/api/docs/` | Interactive Swagger documentation |
| `POST` | `/onlinecourse/course/<id>/submit/` | Submit final exam assessment |
| `GET` | `/onlinecourse/api/showcase/<username>/` | Public student skill portfolio |

---

## 💼 Recruiter & Admin Access
To access the Recruiter Portal:
1. Create a staff user: `python manage.py createsuperuser`
2. Log in and navigate to: `/onlinecourse/recruiters/`

---

## 🧪 Testing
Run the test suite to ensure platform integrity:
```bash
python manage.py test
# For coverage reports:
coverage run manage.py test
coverage report
```

---

## 🤝 Contributing
Contributions are welcome! Please fork the repository and submit a pull request for any features or bug fixes. Ensure all new code includes corresponding tests.

---
*Nexly — Turning Learning into Verified Career Growth.*
